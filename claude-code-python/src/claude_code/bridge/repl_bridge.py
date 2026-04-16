# 原始 TS: bridge/replBridge.ts
"""
REPL Bridge Core

Bootstrap-free core for the Claude Code bridge:
  env registration → session creation → poll loop → ingress WS → teardown.

Reads nothing from bootstrap/state or sessionStorage — all context comes
from params. Caller (init_repl_bridge or a daemon) has already passed
entitlement gates and gathered git/auth/title.

移植自 bridge/replBridge.ts (2406 行)
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING, Any, Awaitable, Callable, Deque, Dict, List,
    Literal, Optional, Protocol, Set, Tuple,
)

# ---------------------------------------------------------------------------
# Lazy / optional imports for un-ported dependencies
# ---------------------------------------------------------------------------

try:
    from .bridge_api import (
        BridgeApiClient, BridgeFatalError,
        create_bridge_api_client,
        is_expired_error_type,
        is_suppressible_403,
        validate_bridge_id,
    )
except ImportError:
    BridgeApiClient = None  # type: ignore[misc,assignment]
    BridgeFatalError = Exception  # type: ignore[misc,assignment]
    create_bridge_api_client = None  # type: ignore[assignment]
    is_expired_error_type = lambda x: False  # type: ignore[assignment]
    is_suppressible_403 = lambda x: False  # type: ignore[assignment]
    validate_bridge_id = lambda x, y: None  # type: ignore[assignment]

try:
    from .types import BridgeConfig
except ImportError:
    BridgeConfig = dict  # type: ignore[assignment,misc]

try:
    from ..utils.debug import log_for_debugging
except ImportError:
    def log_for_debugging(msg: str, **kwargs: Any) -> None:  # type: ignore[misc]
        logging.debug(msg)

try:
    from ..utils.errors import error_message
except ImportError:
    def error_message(e: Any) -> str:  # type: ignore[misc]
        return str(e)

try:
    from ..utils.sleep import sleep as async_sleep
except ImportError:
    async def async_sleep(ms: float, signal: Any = None) -> None:  # type: ignore[misc]
        await asyncio.sleep(ms / 1000)

try:
    from .bridge_messaging import (
        handle_ingress_message,
        handle_server_control_request,
        make_result_message,
        is_eligible_bridge_message,
        extract_title_text,
        BoundedUUIDSet,
    )
except ImportError:
    BoundedUUIDSet = None  # type: ignore[misc,assignment]
    handle_ingress_message = None  # type: ignore[assignment]
    handle_server_control_request = None  # type: ignore[assignment]
    make_result_message = None  # type: ignore[assignment]
    is_eligible_bridge_message = lambda m: False  # type: ignore[assignment]
    extract_title_text = lambda m: None  # type: ignore[assignment]

try:
    from .poll_config_defaults import (
        DEFAULT_POLL_CONFIG,
        PollIntervalConfig,
    )
except ImportError:
    PollIntervalConfig = dict  # type: ignore[assignment,misc]
    DEFAULT_POLL_CONFIG = {  # type: ignore[assignment]
        'poll_interval_ms_not_at_capacity': 5_000,
        'poll_interval_ms_at_capacity': 600_000,
        'non_exclusive_heartbeat_interval_ms': 0,
        'reclaim_older_than_ms': 0,
        'session_keepalive_interval_v2_ms': 0,
    }


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

BridgeState = Literal['ready', 'connected', 'reconnecting', 'failed']


@dataclass
class BridgeCoreParams:
    """
    Explicit-param input to init_bridge_core.

    Everything init_repl_bridge reads from bootstrap state (cwd, session ID,
    git, OAuth) becomes a field here. A daemon caller fills these in itself.
    """
    dir: str
    machine_name: str
    branch: str
    git_repo_url: Optional[str]
    title: str
    base_url: str
    session_ingress_url: str
    worker_type: str
    get_access_token: Callable[[], Optional[str]]
    create_session: Callable[..., Awaitable[Optional[str]]]
    archive_session: Callable[[str], Awaitable[None]]
    get_current_title: Optional[Callable[[], str]] = None
    to_sdk_messages: Optional[Callable[[List[Any]], List[Any]]] = None
    on_auth_401: Optional[Callable[[str], Awaitable[bool]]] = None
    get_poll_interval_config: Optional[Callable[[], Any]] = None
    initial_history_cap: int = 200
    initial_messages: Optional[List[Any]] = None
    previously_flushed_uuids: Optional[Set[str]] = None
    on_inbound_message: Optional[Callable[[Any], None]] = None
    on_permission_response: Optional[Callable[[Any], None]] = None
    on_interrupt: Optional[Callable[[], None]] = None
    on_set_model: Optional[Callable[[Optional[str]], None]] = None
    on_set_max_thinking_tokens: Optional[Callable[[Optional[int]], None]] = None
    on_set_permission_mode: Optional[Callable[[Any], Any]] = None
    on_state_change: Optional[Callable[[BridgeState, Optional[str]], None]] = None
    on_user_message: Optional[Callable[[str, str], bool]] = None
    perpetual: bool = False
    initial_sse_sequence_num: int = 0


# Protocol for transport (ReplBridgeTransport equivalent)
class ReplBridgeTransport(Protocol):
    def connect(self) -> None: ...
    def close(self) -> None: ...
    async def write(self, event: Any) -> None: ...
    async def write_batch(self, events: List[Any]) -> None: ...
    def set_on_connect(self, cb: Callable[[], None]) -> None: ...
    def set_on_data(self, cb: Callable[[Any], None]) -> None: ...
    def set_on_close(self, cb: Callable[[Optional[int]], None]) -> None: ...
    def get_last_sequence_num(self) -> int: ...
    def is_connected_status(self) -> bool: ...
    def get_state_label(self) -> str: ...
    dropped_batch_count: int


@dataclass
class ReplBridgeHandle:
    """Handle returned by init_bridge_core to the caller."""
    bridge_session_id_getter: Callable[[], str]
    environment_id_getter: Callable[[], str]
    session_ingress_url: str
    write_messages: Callable[[List[Any]], None]
    write_sdk_messages: Callable[[List[Any]], None]
    send_control_request: Callable[[Any], None]
    send_control_response: Callable[[Any], None]
    send_control_cancel_request: Callable[[str], None]
    send_result: Callable[[], None]
    teardown: Callable[[], Awaitable[None]]
    get_sse_sequence_num: Optional[Callable[[], int]] = None

    @property
    def bridge_session_id(self) -> str:
        return self.bridge_session_id_getter()

    @property
    def environment_id(self) -> str:
        return self.environment_id_getter()


# ---------------------------------------------------------------------------
# Poll error recovery constants
# ---------------------------------------------------------------------------

POLL_ERROR_INITIAL_DELAY_MS: int = 2_000
POLL_ERROR_MAX_DELAY_MS: int = 60_000
POLL_ERROR_GIVE_UP_MS: int = 15 * 60 * 1000

# Monotonically increasing counter for distinguishing init calls in logs
_init_sequence: int = 0


# ---------------------------------------------------------------------------
# BoundedUUIDSet fallback (if bridge_messaging not ported yet)
# ---------------------------------------------------------------------------

class _BoundedUUIDSet:
    """Ring-buffer bounded set of UUID strings. Evicts oldest on overflow."""

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._set: Set[str] = set()
        self._order: Deque[str] = deque()

    def add(self, uid: str) -> None:
        if uid in self._set:
            return
        self._set.add(uid)
        self._order.append(uid)
        while len(self._order) > self._capacity:
            oldest = self._order.popleft()
            self._set.discard(oldest)

    def has(self, uid: str) -> bool:
        return uid in self._set

    def clear(self) -> None:
        self._set.clear()
        self._order.clear()


def _make_bounded_uuid_set(capacity: int) -> Any:
    if BoundedUUIDSet is not None:
        return BoundedUUIDSet(capacity)
    return _BoundedUUIDSet(capacity)


# ---------------------------------------------------------------------------
# FlushGate: gates message writes during initial flush
# ---------------------------------------------------------------------------

class FlushGate:
    """
    Gates message writes during the initial history flush.

    Between transport connect and flush completion, new messages arriving
    at write_messages() are queued here. After flush, they are drained in
    order. This prevents new messages from interleaving with history.
    """

    def __init__(self) -> None:
        self._active = False
        self._queue: List[Any] = []

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> None:
        """Activate the gate — subsequent enqueue() calls will queue."""
        self._active = True

    def enqueue(self, *messages: Any) -> bool:
        """
        If gate is active, queue messages and return True.
        If inactive, return False (caller should send directly).
        """
        if self._active:
            self._queue.extend(messages)
            return True
        return False

    def end(self) -> List[Any]:
        """Deactivate gate and return queued messages."""
        self._active = False
        msgs = list(self._queue)
        self._queue.clear()
        return msgs

    def deactivate(self) -> None:
        """Deactivate gate without draining (preserve queue)."""
        self._active = False

    def drop(self) -> int:
        """Drop all queued messages, deactivate gate. Returns count dropped."""
        count = len(self._queue)
        self._queue.clear()
        self._active = False
        return count


# ---------------------------------------------------------------------------
# CapacityWake: signal to wake poll loop when transport is lost
# ---------------------------------------------------------------------------

class CapacityWake:
    """
    Signal mechanism to wake the at-capacity poll loop early when transport drops.
    """

    def __init__(self, abort_signal: asyncio.Event) -> None:
        self._abort = abort_signal
        self._event = asyncio.Event()

    def wake(self) -> None:
        """Wake the poll loop (transport was lost)."""
        self._event.set()

    def signal(self) -> 'asyncio.Event':
        """Returns event that is set when woken or aborted."""
        return self._event

    def reset(self) -> None:
        self._event.clear()


# ---------------------------------------------------------------------------
# init_bridge_core
# ---------------------------------------------------------------------------

async def init_bridge_core(
    params: BridgeCoreParams,
) -> Optional[ReplBridgeHandle]:
    """
    Bootstrap-free core: env registration → session creation → poll loop →
    ingress WS → teardown.

    Returns None on registration or session-creation failure.
    """
    global _init_sequence
    _init_sequence += 1
    seq = _init_sequence

    # Unpack params
    dir_ = params.dir
    machine_name = params.machine_name
    branch = params.branch
    git_repo_url = params.git_repo_url
    title = params.title
    base_url = params.base_url
    session_ingress_url = params.session_ingress_url
    worker_type = params.worker_type
    get_access_token = params.get_access_token
    create_session = params.create_session
    archive_session = params.archive_session
    get_current_title = params.get_current_title or (lambda: title)
    to_sdk_messages = params.to_sdk_messages or (lambda _: (_ for _ in ()).throw(
        RuntimeError('BridgeCoreParams.to_sdk_messages not provided.')))
    on_auth_401 = params.on_auth_401
    get_poll_interval_config = params.get_poll_interval_config or (lambda: DEFAULT_POLL_CONFIG)
    initial_history_cap = params.initial_history_cap
    initial_messages = params.initial_messages
    previously_flushed_uuids = params.previously_flushed_uuids
    on_inbound_message = params.on_inbound_message
    on_permission_response = params.on_permission_response
    on_interrupt = params.on_interrupt
    on_set_model = params.on_set_model
    on_set_max_thinking_tokens = params.on_set_max_thinking_tokens
    on_set_permission_mode = params.on_set_permission_mode
    on_state_change = params.on_state_change
    on_user_message = params.on_user_message
    perpetual = params.perpetual
    initial_sse_sequence_num = params.initial_sse_sequence_num

    log_for_debugging(
        f'[bridge:repl] init_bridge_core #{seq} starting '
        f'(initial_messages={len(initial_messages) if initial_messages else 0})'
    )

    # Create bridge API client
    if create_bridge_api_client is None:
        log_for_debugging('[bridge:repl] BridgeApiClient not available — cannot init')
        on_state_change and on_state_change('failed', 'Bridge API not available')
        return None

    api = create_bridge_api_client(
        base_url=base_url,
        get_access_token=get_access_token,
        on_auth_401=on_auth_401,
    )

    bridge_config = {
        'dir': dir_,
        'machine_name': machine_name,
        'branch': branch,
        'git_repo_url': git_repo_url,
        'max_sessions': 1,
        'spawn_mode': 'single-session',
        'verbose': False,
        'sandbox': False,
        'bridge_id': str(uuid.uuid4()),
        'worker_type': worker_type,
        'environment_id': str(uuid.uuid4()),
        'api_base_url': base_url,
        'session_ingress_url': session_ingress_url,
    }

    # 5. Register bridge environment
    environment_id: str
    environment_secret: str
    try:
        reg = await api.register_bridge_environment(bridge_config)
        environment_id = reg['environment_id']
        environment_secret = reg['environment_secret']
    except Exception as err:
        log_for_debugging(
            f'[bridge:repl] Environment registration failed: {error_message(err)}'
        )
        on_state_change and on_state_change('failed', error_message(err))
        return None

    log_for_debugging(f'[bridge:repl] Environment registered: {environment_id}')

    # 6. Create session on the bridge
    current_session_id: str
    try:
        created_session_id = await create_session(
            environment_id=environment_id,
            title=title,
            git_repo_url=git_repo_url,
            branch=branch,
        )
    except Exception as err:
        log_for_debugging(f'[bridge:repl] Session creation failed: {error_message(err)}')
        await _safe_deregister(api, environment_id)
        on_state_change and on_state_change('failed', 'Session creation failed')
        return None

    if not created_session_id:
        log_for_debugging('[bridge:repl] Session creation returned null')
        await _safe_deregister(api, environment_id)
        on_state_change and on_state_change('failed', 'Session creation failed')
        return None

    current_session_id = created_session_id
    log_for_debugging(f'[bridge:repl] Session created: {current_session_id}')

    # UUIDs of initial messages
    initial_message_uuids: Set[str] = set()
    if initial_messages:
        for msg in initial_messages:
            uid = getattr(msg, 'uuid', None) or (msg.get('uuid') if isinstance(msg, dict) else None)
            if uid:
                initial_message_uuids.add(uid)

    recent_posted_uuids = _make_bounded_uuid_set(2000)
    for uid in initial_message_uuids:
        recent_posted_uuids.add(uid)

    recent_inbound_uuids = _make_bounded_uuid_set(2000)

    # Abort controller for poll loop
    poll_abort = asyncio.Event()  # set = aborted
    transport: Optional[Any] = None
    v2_generation: int = 0
    last_transport_sequence_num: int = 0
    current_work_id: Optional[str] = None
    current_ingress_token: Optional[str] = None
    capacity_wake = CapacityWake(poll_abort)
    flush_gate = FlushGate()
    user_message_callback_done = not on_user_message
    environment_recreations = 0
    reconnect_task: Optional[asyncio.Task] = None
    teardown_started = False

    # Mutable closure state (wrapped in a list so closures can rebind)
    _state: Dict[str, Any] = {
        'current_session_id': current_session_id,
        'environment_id': environment_id,
        'environment_secret': environment_secret,
        'transport': None,
        'v2_generation': 0,
        'last_transport_sequence_num': 0,
        'current_work_id': None,
        'current_ingress_token': None,
        'environment_recreations': 0,
        'teardown_started': False,
        'user_message_callback_done': user_message_callback_done,
    }

    async def try_reconnect_in_place(requested_env_id: str, session_id: str) -> bool:
        if _state['environment_id'] != requested_env_id:
            log_for_debugging(
                f'[bridge:repl] Env mismatch (requested {requested_env_id}, '
                f'got {_state["environment_id"]}) — cannot reconnect in place'
            )
            return False
        try:
            await api.reconnect_session(_state['environment_id'], session_id)
            log_for_debugging(
                f'[bridge:repl] Reconnected session {session_id} in place on env '
                f'{_state["environment_id"]}'
            )
            return True
        except Exception as err:
            log_for_debugging(
                f'[bridge:repl] reconnect_session({session_id}) failed: '
                f'{error_message(err)}'
            )
            return False

    _reconnect_promise: Optional[asyncio.Task] = None

    async def reconnect_environment_with_session() -> bool:
        nonlocal _reconnect_promise
        if _reconnect_promise is not None and not _reconnect_promise.done():
            return await _reconnect_promise
        task = asyncio.ensure_future(_do_reconnect())
        _reconnect_promise = task
        try:
            return await task
        finally:
            _reconnect_promise = None

    async def _do_reconnect() -> bool:
        _state['environment_recreations'] += 1
        _state['v2_generation'] += 1
        n = _state['environment_recreations']
        log_for_debugging(
            f'[bridge:repl] Reconnecting after env lost '
            f'(attempt {n}/3)'
        )
        if n > 3:
            log_for_debugging('[bridge:repl] Environment reconnect limit reached, giving up')
            return False

        tr = _state['transport']
        if tr is not None:
            seq = tr.get_last_sequence_num()
            if seq > _state['last_transport_sequence_num']:
                _state['last_transport_sequence_num'] = seq
            tr.close()
            _state['transport'] = None

        capacity_wake.wake()
        flush_gate.drop()

        # Release current work item
        if _state['current_work_id']:
            work_id_being_cleared = _state['current_work_id']
            try:
                await api.stop_work(_state['environment_id'], work_id_being_cleared, False)
            except Exception:
                pass
            if _state['current_work_id'] != work_id_being_cleared:
                log_for_debugging('[bridge:repl] Poll loop recovered during stopWork — deferring')
                _state['environment_recreations'] = 0
                return True
            _state['current_work_id'] = None
            _state['current_ingress_token'] = None

        if poll_abort.is_set():
            log_for_debugging('[bridge:repl] Reconnect aborted by teardown')
            return False

        requested_env_id = _state['environment_id']
        bridge_config['reuse_environment_id'] = requested_env_id
        try:
            reg = await api.register_bridge_environment(bridge_config)
            _state['environment_id'] = reg['environment_id']
            _state['environment_secret'] = reg['environment_secret']
        except Exception as err:
            bridge_config.pop('reuse_environment_id', None)
            log_for_debugging(
                f'[bridge:repl] Environment re-registration failed: {error_message(err)}'
            )
            return False
        bridge_config.pop('reuse_environment_id', None)

        if poll_abort.is_set():
            await _safe_deregister(api, _state['environment_id'])
            return False

        if _state['transport'] is not None:
            log_for_debugging('[bridge:repl] Poll loop recovered during re-register — deferring')
            _state['environment_recreations'] = 0
            return True

        # Strategy 1: reconnect in place
        if await try_reconnect_in_place(requested_env_id, _state['current_session_id']):
            _state['environment_recreations'] = 0
            return True

        # Strategy 2: fresh session
        await archive_session(_state['current_session_id'])

        if poll_abort.is_set():
            await _safe_deregister(api, _state['environment_id'])
            return False

        current_title = get_current_title()
        try:
            new_session_id = await asyncio.wait_for(
                create_session(
                    environment_id=_state['environment_id'],
                    title=current_title,
                    git_repo_url=git_repo_url,
                    branch=branch,
                ),
                timeout=15.0,
            )
        except Exception as err:
            log_for_debugging(
                f'[bridge:repl] Session creation failed during reconnection: '
                f'{error_message(err)}'
            )
            return False

        if not new_session_id:
            log_for_debugging('[bridge:repl] Session creation failed during reconnection (null)')
            return False

        if poll_abort.is_set():
            await archive_session(new_session_id)
            return False

        _state['current_session_id'] = new_session_id
        _state['last_transport_sequence_num'] = 0
        recent_inbound_uuids.clear()
        _state['user_message_callback_done'] = not on_user_message
        _state['environment_recreations'] = 0

        if previously_flushed_uuids is not None:
            previously_flushed_uuids.clear()

        log_for_debugging(f'[bridge:repl] Re-created session: {new_session_id}')
        return True

    def drain_flush_gate() -> None:
        msgs = flush_gate.end()
        if not msgs:
            return
        tr = _state['transport']
        if tr is None:
            log_for_debugging(
                f'[bridge:repl] Cannot drain {len(msgs)} pending message(s): no transport'
            )
            return
        for msg in msgs:
            uid = getattr(msg, 'uuid', None) or (msg.get('uuid') if isinstance(msg, dict) else None)
            if uid:
                recent_posted_uuids.add(uid)
        if to_sdk_messages is not None:
            sdk_msgs = to_sdk_messages(msgs)
        else:
            sdk_msgs = msgs
        events = [{**m, 'session_id': _state['current_session_id']}
                  for m in (sdk_msgs if isinstance(sdk_msgs, list) else list(sdk_msgs))]
        log_for_debugging(f'[bridge:repl] Drained {len(msgs)} pending message(s) after flush')
        asyncio.ensure_future(tr.write_batch(events))

    do_teardown_impl: Optional[Callable[[], Awaitable[None]]] = None

    def trigger_teardown() -> None:
        if do_teardown_impl:
            asyncio.ensure_future(do_teardown_impl())

    def handle_transport_permanent_close(close_code: Optional[int]) -> None:
        log_for_debugging(f'[bridge:repl] Transport permanently closed: code={close_code}')
        tr = _state['transport']
        if tr is not None:
            closed_seq = tr.get_last_sequence_num()
            if closed_seq > _state['last_transport_sequence_num']:
                _state['last_transport_sequence_num'] = closed_seq
            _state['transport'] = None

        capacity_wake.wake()
        dropped = flush_gate.drop()
        if dropped > 0:
            log_for_debugging(
                f'[bridge:repl] Dropping {dropped} pending message(s) on transport close '
                f'(code={close_code})'
            )

        if close_code == 1000:
            on_state_change and on_state_change('failed', 'session ended')
            poll_abort.set()
            trigger_teardown()
            return

        on_state_change and on_state_change(
            'reconnecting',
            f'Remote Control connection lost (code {close_code})'
        )
        log_for_debugging(
            f'[bridge:repl] Transport reconnect budget exhausted (code={close_code}), '
            'attempting env reconnect'
        )

        async def _reconnect_then_check() -> None:
            success = await reconnect_environment_with_session()
            if success:
                return
            if poll_abort.is_set():
                return
            log_for_debugging(
                '[bridge:repl] reconnect_environment_with_session resolved False — tearing down'
            )
            on_state_change and on_state_change('failed', 'reconnection failed')
            trigger_teardown()

        asyncio.ensure_future(_reconnect_then_check())

    def on_work_received(
        work_session_id: str,
        ingress_token: str,
        work_id: str,
        server_use_ccr_v2: bool,
    ) -> None:
        nonlocal initial_message_uuids

        log_for_debugging(
            f'[bridge:repl] Work received: workId={work_id} '
            f'workSessionId={work_session_id} '
            f'currentSessionId={_state["current_session_id"]}'
        )

        # Refresh crash-recovery pointer (no-op in Python port — pointer logic not ported)
        _state['current_work_id'] = work_id
        _state['current_ingress_token'] = ingress_token

        # Reject foreign sessions
        if work_session_id != _state['current_session_id']:
            # Compare ignoring tag prefix (session_* vs cse_*)
            def _uuid_part(s: str) -> str:
                idx = s.find('_')
                return s[idx + 1:] if idx >= 0 else s

            if _uuid_part(work_session_id) != _uuid_part(_state['current_session_id']):
                log_for_debugging(
                    f'[bridge:repl] Rejecting foreign session: '
                    f'expected={_state["current_session_id"]} got={work_session_id}'
                )
                return

        # Close old transport
        old_tr = _state['transport']
        if old_tr is not None:
            old_tr_captured = old_tr
            _state['transport'] = None
            old_seq = old_tr_captured.get_last_sequence_num()
            if old_seq > _state['last_transport_sequence_num']:
                _state['last_transport_sequence_num'] = old_seq
            old_tr_captured.close()

        flush_gate.deactivate()
        _state['v2_generation'] += 1
        initial_flush_done = [False]  # mutable cell

        # NOTE: v1 transport (HybridTransport) construction is not ported yet.
        # We create a stub transport that handles the basic interface.
        # Callers that provide a transport_factory can override.
        log_for_debugging(
            f'[bridge:repl] Work received but transport construction not fully ported '
            f'(work_id={work_id}). Session-ingress connection requires HybridTransport.'
        )

        # Signal connected state after short delay (stub behavior)
        async def _stub_connect() -> None:
            on_state_change and on_state_change('connected')

        asyncio.ensure_future(_stub_connect())

    # 7. Start poll loop
    poll_task = asyncio.ensure_future(
        _start_work_poll_loop(
            api=api,
            get_credentials=lambda: {
                'environment_id': _state['environment_id'],
                'environment_secret': _state['environment_secret'],
            },
            signal=poll_abort,
            get_poll_interval_config=get_poll_interval_config,
            on_state_change=on_state_change,
            on_work_received=on_work_received,
            is_at_capacity=lambda: _state['transport'] is not None,
            capacity_wake=capacity_wake,
            on_fatal_error=trigger_teardown,
            get_ws_state=lambda: (_state['transport'].get_state_label()
                                  if _state['transport'] else 'null'),
            get_heartbeat_info=lambda: (
                {
                    'environment_id': _state['environment_id'],
                    'work_id': _state['current_work_id'],
                    'session_token': _state['current_ingress_token'],
                }
                if _state['current_work_id'] and _state['current_ingress_token']
                else None
            ),
            on_heartbeat_fatal=lambda err: _on_heartbeat_fatal(err),
            on_environment_lost=lambda: reconnect_environment_with_session().then_creds(  # type: ignore[attr-defined]
                lambda success: ({'environment_id': _state['environment_id'],
                                  'environment_secret': _state['environment_secret']}
                                 if success else None)
            ),
        )
    )

    # Keep_alive timer (disabled if interval = 0)
    keep_alive_timer: Optional[asyncio.Task] = None
    keep_alive_interval_ms = get_poll_interval_config().get(
        'session_keepalive_interval_v2_ms', 0)
    if keep_alive_interval_ms > 0:
        async def _keep_alive_loop() -> None:
            while not poll_abort.is_set():
                await asyncio.sleep(keep_alive_interval_ms / 1000)
                if _state['transport'] and not poll_abort.is_set():
                    try:
                        await _state['transport'].write({'type': 'keep_alive'})
                        log_for_debugging('[bridge:repl] keep_alive sent')
                    except Exception as err:
                        log_for_debugging(
                            f'[bridge:repl] keep_alive write failed: {error_message(err)}'
                        )

        keep_alive_timer = asyncio.ensure_future(_keep_alive_loop())

    def _on_heartbeat_fatal(err: Any) -> None:
        log_for_debugging(
            f'[bridge:repl] heartbeatWork fatal — tearing down work item for fast re-dispatch'
        )
        tr = _state['transport']
        if tr is not None:
            seq = tr.get_last_sequence_num()
            if seq > _state['last_transport_sequence_num']:
                _state['last_transport_sequence_num'] = seq
            tr.close()
            _state['transport'] = None
        flush_gate.drop()
        if _state['current_work_id']:
            asyncio.ensure_future(
                api.stop_work(_state['environment_id'], _state['current_work_id'], False)
            )
        _state['current_work_id'] = None
        _state['current_ingress_token'] = None
        capacity_wake.wake()
        on_state_change and on_state_change(
            'reconnecting', 'Work item lease expired, fetching fresh token'
        )

    # Teardown
    async def _do_teardown() -> None:
        if _state['teardown_started']:
            log_for_debugging('[bridge:repl] Teardown already in progress, skipping')
            return
        _state['teardown_started'] = True
        teardown_start = time.time()
        log_for_debugging(
            f'[bridge:repl] Teardown starting: env={_state["environment_id"]} '
            f'session={_state["current_session_id"]}'
        )

        if keep_alive_timer is not None:
            keep_alive_timer.cancel()

        poll_abort.set()
        log_for_debugging('[bridge:repl] Teardown: poll loop aborted')

        tr = _state['transport']
        if tr is not None:
            final_seq = tr.get_last_sequence_num()
            if final_seq > _state['last_transport_sequence_num']:
                _state['last_transport_sequence_num'] = final_seq

        if perpetual:
            _state['transport'] = None
            flush_gate.drop()
            log_for_debugging(
                f'[bridge:repl] Teardown (perpetual): leaving '
                f'env={_state["environment_id"]} '
                f'session={_state["current_session_id"]} alive on server, '
                f'duration={int((time.time() - teardown_start) * 1000)}ms'
            )
            return

        teardown_transport = _state['transport']
        _state['transport'] = None
        flush_gate.drop()

        if teardown_transport and make_result_message:
            try:
                await teardown_transport.write(
                    make_result_message(_state['current_session_id'])
                )
            except Exception:
                pass

        stop_work_coro = None
        if _state['current_work_id']:
            async def _stop_work() -> None:
                try:
                    await api.stop_work(
                        _state['environment_id'], _state['current_work_id'], True
                    )
                    log_for_debugging('[bridge:repl] Teardown: stopWork completed')
                except Exception as err:
                    log_for_debugging(
                        f'[bridge:repl] Teardown stopWork failed: {error_message(err)}'
                    )
            stop_work_coro = _stop_work()

        archive_coro = archive_session(_state['current_session_id'])
        tasks_to_await = [t for t in [stop_work_coro, archive_coro] if t is not None]
        if tasks_to_await:
            await asyncio.gather(*tasks_to_await, return_exceptions=True)

        if teardown_transport:
            teardown_transport.close()
            log_for_debugging('[bridge:repl] Teardown: transport closed')

        try:
            await api.deregister_environment(_state['environment_id'])
        except Exception as err:
            log_for_debugging(
                f'[bridge:repl] Teardown deregister failed: {error_message(err)}'
            )

        log_for_debugging(
            f'[bridge:repl] Teardown complete: env={_state["environment_id"]} '
            f'duration={int((time.time() - teardown_start) * 1000)}ms'
        )

    do_teardown_impl = _do_teardown

    log_for_debugging(
        f'[bridge:repl] Ready: env={_state["environment_id"]} '
        f'session={_state["current_session_id"]}'
    )
    on_state_change and on_state_change('ready')

    # -----------------------------------------------------------------------
    # Handle methods
    # -----------------------------------------------------------------------

    def _write_messages(messages: List[Any]) -> None:
        if is_eligible_bridge_message is None:
            return
        filtered = [
            m for m in messages
            if is_eligible_bridge_message(m)
            and _get_uuid(m) not in initial_message_uuids
            and not recent_posted_uuids.has(_get_uuid(m))
        ]
        if not filtered:
            return

        if not _state['user_message_callback_done'] and on_user_message:
            for m in filtered:
                text = extract_title_text(m) if extract_title_text else None
                if text is not None and on_user_message(text, _state['current_session_id']):
                    _state['user_message_callback_done'] = True
                    break

        if flush_gate.enqueue(*filtered):
            log_for_debugging(
                f'[bridge:repl] Queued {len(filtered)} message(s) during initial flush'
            )
            return

        tr = _state['transport']
        if tr is None:
            log_for_debugging(
                f'[bridge:repl] Transport not configured, dropping {len(filtered)} message(s)',
            )
            return

        for msg in filtered:
            uid = _get_uuid(msg)
            if uid:
                recent_posted_uuids.add(uid)

        if to_sdk_messages:
            sdk_msgs = to_sdk_messages(filtered)
        else:
            sdk_msgs = filtered

        events = [{**m, 'session_id': _state['current_session_id']}
                  for m in (sdk_msgs if isinstance(sdk_msgs, list) else list(sdk_msgs))]
        asyncio.ensure_future(tr.write_batch(events))

    def _write_sdk_messages(messages: List[Any]) -> None:
        filtered = [
            m for m in messages
            if not (_get_uuid(m) and recent_posted_uuids.has(_get_uuid(m)))
        ]
        if not filtered:
            return
        tr = _state['transport']
        if tr is None:
            log_for_debugging(
                f'[bridge:repl] Transport not configured, dropping {len(filtered)} SDK message(s)'
            )
            return
        for msg in filtered:
            uid = _get_uuid(msg)
            if uid:
                recent_posted_uuids.add(uid)
        events = [{**m, 'session_id': _state['current_session_id']}
                  for m in filtered]
        asyncio.ensure_future(tr.write_batch(events))

    def _send_control_request(request: Any) -> None:
        tr = _state['transport']
        if tr is None:
            log_for_debugging('[bridge:repl] Transport not configured, skipping control_request')
            return
        event = {**request, 'session_id': _state['current_session_id']}
        asyncio.ensure_future(tr.write(event))

    def _send_control_response(response: Any) -> None:
        tr = _state['transport']
        if tr is None:
            log_for_debugging('[bridge:repl] Transport not configured, skipping control_response')
            return
        event = {**response, 'session_id': _state['current_session_id']}
        asyncio.ensure_future(tr.write(event))

    def _send_control_cancel_request(request_id: str) -> None:
        tr = _state['transport']
        if tr is None:
            log_for_debugging(
                '[bridge:repl] Transport not configured, skipping control_cancel_request'
            )
            return
        event = {
            'type': 'control_cancel_request',
            'request_id': request_id,
            'session_id': _state['current_session_id'],
        }
        asyncio.ensure_future(tr.write(event))

    def _send_result() -> None:
        tr = _state['transport']
        if tr is None:
            log_for_debugging('[bridge:repl] sendResult: skipping, transport not configured')
            return
        if make_result_message:
            asyncio.ensure_future(
                tr.write(make_result_message(_state['current_session_id']))
            )

    def _get_sse_sequence_num() -> int:
        live = (_state['transport'].get_last_sequence_num()
                if _state['transport'] else 0)
        return max(_state['last_transport_sequence_num'], live)

    return ReplBridgeHandle(
        bridge_session_id_getter=lambda: _state['current_session_id'],
        environment_id_getter=lambda: _state['environment_id'],
        session_ingress_url=session_ingress_url,
        write_messages=_write_messages,
        write_sdk_messages=_write_sdk_messages,
        send_control_request=_send_control_request,
        send_control_response=_send_control_response,
        send_control_cancel_request=_send_control_cancel_request,
        send_result=_send_result,
        teardown=_do_teardown,
        get_sse_sequence_num=_get_sse_sequence_num,
    )


# ---------------------------------------------------------------------------
# Work poll loop
# ---------------------------------------------------------------------------

async def _start_work_poll_loop(
    *,
    api: Any,
    get_credentials: Callable[[], Dict[str, str]],
    signal: asyncio.Event,
    on_state_change: Optional[Callable[[BridgeState, Optional[str]], None]],
    on_work_received: Callable[[str, str, str, bool], None],
    on_environment_lost: Optional[Callable[[], Awaitable[Optional[Dict[str, str]]]]] = None,
    get_ws_state: Optional[Callable[[], str]] = None,
    is_at_capacity: Optional[Callable[[], bool]] = None,
    capacity_wake: Optional[CapacityWake] = None,
    on_fatal_error: Optional[Callable[[], None]] = None,
    get_poll_interval_config: Callable[[], Any] = lambda: DEFAULT_POLL_CONFIG,
    get_heartbeat_info: Optional[Callable[[], Optional[Dict[str, str]]]] = None,
    on_heartbeat_fatal: Optional[Callable[[Any], None]] = None,
) -> None:
    """
    Persistent poll loop for work items.

    When a work item arrives, acknowledges it and calls on_work_received.
    Continues polling so the server can dispatch fresh work on reconnect.
    """
    MAX_ENVIRONMENT_RECREATIONS = 3
    log_for_debugging(
        f'[bridge:repl] Starting work poll loop for env='
        f'{get_credentials()["environment_id"]}'
    )

    consecutive_errors = 0
    first_error_time: Optional[float] = None
    last_poll_error_time: Optional[float] = None
    environment_recreations = 0
    suspension_detected = False

    while not signal.is_set():
        creds = get_credentials()
        env_id = creds['environment_id']
        env_secret = creds['environment_secret']
        poll_config = get_poll_interval_config()

        try:
            work = await api.poll_for_work(
                env_id,
                env_secret,
                signal,
                poll_config.get('reclaim_older_than_ms', 0),
            )

            environment_recreations = 0
            if consecutive_errors > 0:
                log_for_debugging(
                    f'[bridge:repl] Poll recovered after {consecutive_errors} consecutive error(s)'
                )
                consecutive_errors = 0
                first_error_time = None
                last_poll_error_time = None
                on_state_change and on_state_change('ready')

            if not work:
                skip_at_capacity_once = suspension_detected
                suspension_detected = False

                at_cap = is_at_capacity() if is_at_capacity else False
                if at_cap and capacity_wake and not skip_at_capacity_once:
                    at_cap_ms = poll_config.get('poll_interval_ms_at_capacity', 600_000)
                    hb_ms = poll_config.get('non_exclusive_heartbeat_interval_ms', 0)

                    # Heartbeat loop
                    if hb_ms > 0 and get_heartbeat_info:
                        poll_deadline = (time.time() + at_cap_ms / 1000
                                         if at_cap_ms > 0 else None)
                        needs_backoff = False
                        hb_cycles = 0

                        while (not signal.is_set() and
                               (is_at_capacity() if is_at_capacity else False) and
                               (poll_deadline is None or time.time() < poll_deadline)):
                            hb_cfg = get_poll_interval_config()
                            if hb_cfg.get('non_exclusive_heartbeat_interval_ms', 0) <= 0:
                                break

                            info = get_heartbeat_info()
                            if not info:
                                break

                            try:
                                await api.heartbeat_work(
                                    info['environment_id'],
                                    info['work_id'],
                                    info['session_token'],
                                )
                            except Exception as err:
                                if isinstance(err, BridgeFatalError if BridgeFatalError is not Exception else type(None)):
                                    if on_heartbeat_fatal:
                                        on_heartbeat_fatal(err)
                                    else:
                                        needs_backoff = True
                                    break

                            hb_cycles += 1
                            await asyncio.sleep(
                                hb_cfg['non_exclusive_heartbeat_interval_ms'] / 1000
                            )

                        if not needs_backoff:
                            continue

                    # At-capacity sleep
                    sleep_ms = (at_cap_ms if at_cap_ms > 0 else hb_ms)
                    if sleep_ms > 0:
                        sleep_start = time.time()
                        try:
                            await asyncio.wait_for(
                                _wait_for_event(capacity_wake.signal()),
                                timeout=sleep_ms / 1000,
                            )
                        except asyncio.TimeoutError:
                            pass

                        overrun_ms = (time.time() - sleep_start) * 1000 - sleep_ms
                        if overrun_ms > 60_000:
                            log_for_debugging(
                                f'[bridge:repl] At-capacity sleep overran by '
                                f'{int(overrun_ms / 1000)}s — suspension detected'
                            )
                            suspension_detected = True
                        capacity_wake.reset()
                else:
                    not_at_cap_ms = poll_config.get('poll_interval_ms_not_at_capacity', 5_000)
                    await asyncio.sleep(not_at_cap_ms / 1000)
                continue

            # Decode work secret
            try:
                from .work_secret import decode_work_secret  # type: ignore[import]
                secret = decode_work_secret(work.get('secret', ''))
            except (ImportError, Exception) as err:
                log_for_debugging(
                    f'[bridge:repl] Failed to decode work secret: {error_message(err)}'
                )
                try:
                    await api.stop_work(env_id, work.get('id', ''), False)
                except Exception:
                    pass
                continue

            # Acknowledge
            try:
                await api.acknowledge_work(
                    env_id, work.get('id', ''), secret.get('session_ingress_token', '')
                )
            except Exception as err:
                log_for_debugging(
                    f'[bridge:repl] Acknowledge failed workId={work.get("id")}: '
                    f'{error_message(err)}'
                )

            work_data = work.get('data', {})
            if work_data.get('type') == 'healthcheck':
                log_for_debugging('[bridge:repl] Healthcheck received')
                continue

            if work_data.get('type') == 'session':
                work_session_id = work_data.get('id', '')
                on_work_received(
                    work_session_id,
                    secret.get('session_ingress_token', ''),
                    work.get('id', ''),
                    bool(secret.get('use_code_sessions', False)),
                )
                log_for_debugging('[bridge:repl] Work accepted, continuing poll loop')

        except Exception as err:
            if signal.is_set():
                break

            # Environment deleted (404)
            is_fatal = isinstance(err, BridgeFatalError if BridgeFatalError is not Exception else type(None))
            if is_fatal and getattr(err, 'status', None) == 404 and on_environment_lost:
                current_env_id = get_credentials()['environment_id']
                if env_id != current_env_id:
                    log_for_debugging(
                        f'[bridge:repl] Stale poll error for old env={env_id}, '
                        f'current env={current_env_id} — skipping onEnvironmentLost'
                    )
                    consecutive_errors = 0
                    first_error_time = None
                    continue

                environment_recreations += 1
                log_for_debugging(
                    f'[bridge:repl] Environment deleted, attempting re-registration '
                    f'(attempt {environment_recreations}/{MAX_ENVIRONMENT_RECREATIONS})'
                )

                if environment_recreations > MAX_ENVIRONMENT_RECREATIONS:
                    log_for_debugging('[bridge:repl] Environment re-registration limit reached')
                    on_state_change and on_state_change('failed', 'env lost, limit reached')
                    on_fatal_error and on_fatal_error()
                    break

                on_state_change and on_state_change('reconnecting', 'environment lost')
                new_creds = await on_environment_lost()
                if signal.is_set():
                    break
                if new_creds:
                    consecutive_errors = 0
                    first_error_time = None
                    on_state_change and on_state_change('ready')
                    continue
                on_state_change and on_state_change('failed', 'env lost, re-registration failed')
                on_fatal_error and on_fatal_error()
                break

            # Other fatal errors
            if is_fatal:
                log_for_debugging(f'[bridge:repl] Fatal poll error: {err}')
                on_state_change and on_state_change('failed', str(err))
                on_fatal_error and on_fatal_error()
                break

            # Transient errors — exponential backoff
            now = time.time()
            if (last_poll_error_time is not None and
                    (now - last_poll_error_time) > POLL_ERROR_MAX_DELAY_MS * 2 / 1000):
                log_for_debugging('[bridge:repl] Detected system sleep, resetting poll error budget')
                consecutive_errors = 0
                first_error_time = None
            last_poll_error_time = now

            consecutive_errors += 1
            if first_error_time is None:
                first_error_time = now
            elapsed_ms = int((now - first_error_time) * 1000)

            ws_label = (get_ws_state() if get_ws_state else 'unknown')
            log_for_debugging(
                f'[bridge:repl] Poll error (attempt {consecutive_errors}, '
                f'elapsed {int(elapsed_ms / 1000)}s, ws={ws_label}): '
                f'{error_message(err)}'
            )

            if consecutive_errors == 1:
                on_state_change and on_state_change('reconnecting', error_message(err))

            if elapsed_ms >= POLL_ERROR_GIVE_UP_MS:
                log_for_debugging(
                    f'[bridge:repl] Poll failures exceeded {POLL_ERROR_GIVE_UP_MS // 1000}s, giving up'
                )
                on_state_change and on_state_change('failed', 'connection to server lost')
                break

            # Exponential backoff: 2s → 4s → 8s → ... → 60s cap
            backoff_ms = min(
                POLL_ERROR_INITIAL_DELAY_MS * (2 ** (consecutive_errors - 1)),
                POLL_ERROR_MAX_DELAY_MS,
            )

            # Heartbeat during backoff
            hb_cfg = get_poll_interval_config()
            if hb_cfg.get('non_exclusive_heartbeat_interval_ms', 0) > 0 and get_heartbeat_info:
                info = get_heartbeat_info()
                if info:
                    try:
                        await api.heartbeat_work(
                            info['environment_id'],
                            info['work_id'],
                            info['session_token'],
                        )
                    except Exception:
                        pass

            await asyncio.sleep(backoff_ms / 1000)

    log_for_debugging(
        f'[bridge:repl] Work poll loop ended '
        f'(aborted={signal.is_set()}) '
        f'env={get_credentials()["environment_id"]}'
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

async def _wait_for_event(event: asyncio.Event) -> None:
    """Wait until event is set."""
    while not event.is_set():
        await asyncio.sleep(0.05)


async def _safe_deregister(api: Any, environment_id: str) -> None:
    try:
        await api.deregister_environment(environment_id)
    except Exception:
        pass


def _get_uuid(msg: Any) -> str:
    if isinstance(msg, dict):
        return msg.get('uuid', '') or ''
    return getattr(msg, 'uuid', '') or ''


# ---------------------------------------------------------------------------
# Exported for testing (mirrors TS export pattern)
# ---------------------------------------------------------------------------

_start_work_poll_loop_for_testing = _start_work_poll_loop
_POLL_ERROR_INITIAL_DELAY_MS_FOR_TESTING = POLL_ERROR_INITIAL_DELAY_MS
_POLL_ERROR_MAX_DELAY_MS_FOR_TESTING = POLL_ERROR_MAX_DELAY_MS
_POLL_ERROR_GIVE_UP_MS_FOR_TESTING = POLL_ERROR_GIVE_UP_MS
