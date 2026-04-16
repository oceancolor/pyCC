# 原始 TS: utils/swarm/inProcessRunner.ts
"""
In-process teammate runner

Wraps run_agent() for in-process teammates, providing:
- Permission request proxying to the team leader
- Graceful shutdown on receipt of shutdown requests
- Teammate message injection (leader → teammate)
- Model override support

移植自 utils/swarm/inProcessRunner.ts (1552 行)
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING, Any, AsyncIterator, Callable, Dict, Iterator, List,
    Literal, Optional, Set, Tuple, TypedDict,
)

# ---------------------------------------------------------------------------
# Lazy/optional imports for un-ported dependencies
# ---------------------------------------------------------------------------
if TYPE_CHECKING:
    # These imports are type-only to avoid circular dependencies
    pass

try:
    from ...utils.debug import log_for_debugging
except ImportError:
    def log_for_debugging(msg: str, **kwargs: Any) -> None:  # type: ignore[misc]
        pass

try:
    from ..swarm.constants import TEAM_LEAD_NAME
except ImportError:
    TEAM_LEAD_NAME = 'TeamLead'

# ---------------------------------------------------------------------------
# TypedDict / dataclass types
# ---------------------------------------------------------------------------

class ShutdownRequest(TypedDict):
    """Structured shutdown request sent from leader to teammate."""
    type: Literal['shutdown']
    reason: str


class PermissionRequest(TypedDict, total=False):
    """Permission request from a teammate, sent upstream to the leader."""
    type: Literal['permission_request']
    request_id: str
    tool_name: str
    tool_input: Dict[str, Any]
    teammate_name: str


class PermissionResponse(TypedDict, total=False):
    """Permission response from the leader back to the teammate."""
    type: Literal['permission_response']
    request_id: str
    approved: bool
    denial_reason: Optional[str]


class TeammateMessage(TypedDict, total=False):
    """A message injected into a teammate's conversation by the leader."""
    role: Literal['user', 'assistant']
    content: str
    # Internal metadata
    text: str
    is_injected: bool


class InProcessRunnerConfig(TypedDict, total=False):
    """Configuration for running an in-process teammate."""
    teammate_name: str
    system_prompt: str
    model: Optional[str]
    max_tokens: Optional[int]
    tool_use_context: Any  # ToolUseContext — unported
    allowed_tools: List[str]
    invoking_request_id: Optional[str]


class InProcessRunnerResult(TypedDict, total=False):
    """Result from running an in-process teammate."""
    success: bool
    output: str
    error: Optional[str]
    messages: List[Any]
    stop_reason: str
    permission_wait_ms: int


# ---------------------------------------------------------------------------
# Task model (matches swarm task lifecycle)
# ---------------------------------------------------------------------------

TaskStatus = Literal['pending', 'in_progress', 'completed', 'failed']


@dataclass
class SwarmTask:
    """A unit of work assigned to a teammate."""
    id: str
    description: str
    assignee: str
    status: TaskStatus = 'pending'
    result: Optional[str] = None
    error: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


def find_pending_task(tasks: List[SwarmTask], assignee: str) -> Optional[SwarmTask]:
    """Find the first pending task for a given assignee."""
    return next(
        (task for task in tasks
         if task.status == 'pending' and task.assignee == assignee),
        None
    )


def find_task_by_id(tasks: List[SwarmTask], task_id: str) -> Optional[SwarmTask]:
    return next((t for t in tasks if t.id == task_id), None)


# ---------------------------------------------------------------------------
# Shutdown / interrupt parsing
# ---------------------------------------------------------------------------

SHUTDOWN_TAG = '<SHUTDOWN>'
SHUTDOWN_REASON_TAG = '<REASON>'


def parse_shutdown_request(text: str) -> Optional[ShutdownRequest]:
    """
    Parse a shutdown request from a message text.
    The leader sends a structured shutdown message like:
        <SHUTDOWN><REASON>Task completed successfully</REASON></SHUTDOWN>
    or just <SHUTDOWN> with no reason.
    """
    if SHUTDOWN_TAG not in text:
        return None
    reason = 'Shutdown requested by team leader'
    reason_match = text.find(SHUTDOWN_REASON_TAG)
    end_tag = f'</{SHUTDOWN_REASON_TAG[1:]}'
    if reason_match >= 0:
        start = reason_match + len(SHUTDOWN_REASON_TAG)
        end = text.find(end_tag, start)
        if end > start:
            reason = text[start:end].strip()
    return ShutdownRequest(type='shutdown', reason=reason)


# ---------------------------------------------------------------------------
# Permission proxy helpers
# ---------------------------------------------------------------------------

class PermissionBridge:
    """
    Bridges permission requests from an in-process teammate to the leader.

    The teammate calls request_permission() with a tool name and input.
    The leader's onPermissionRequest callback is invoked.
    When the leader responds, the waiter is released.
    """

    def __init__(self) -> None:
        self._pending: Dict[str, asyncio.Future[PermissionResponse]] = {}

    def make_request_id(self) -> str:
        import uuid
        return str(uuid.uuid4())

    async def request_permission(
        self,
        request_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        teammate_name: str,
        on_request: Callable[[PermissionRequest], None],
    ) -> PermissionResponse:
        """
        Send a permission request and wait for the leader's response.
        """
        loop = asyncio.get_event_loop()
        future: asyncio.Future[PermissionResponse] = loop.create_future()
        self._pending[request_id] = future

        req = PermissionRequest(
            type='permission_request',
            request_id=request_id,
            tool_name=tool_name,
            tool_input=tool_input,
            teammate_name=teammate_name,
        )
        on_request(req)

        return await future

    def resolve_permission(self, response: PermissionResponse) -> None:
        """Called by the leader to resolve a pending permission request."""
        request_id = response.get('request_id', '')
        future = self._pending.pop(request_id, None)
        if future and not future.done():
            future.set_result(response)

    def reject_all(self, reason: str = 'Teammate shutting down') -> None:
        """Reject all pending permission requests (e.g. on shutdown)."""
        for request_id, future in list(self._pending.items()):
            if not future.done():
                future.set_result(PermissionResponse(
                    type='permission_response',
                    request_id=request_id,
                    approved=False,
                    denial_reason=reason,
                ))
        self._pending.clear()


# ---------------------------------------------------------------------------
# In-process runner state
# ---------------------------------------------------------------------------

@dataclass
class InProcessRunnerState:
    """
    Mutable state for an in-process teammate runner.
    Tracks permission wait time, pending user messages, and shutdown state.
    """
    teammate_name: str
    config: InProcessRunnerConfig
    permission_bridge: PermissionBridge = field(default_factory=PermissionBridge)
    shutdown_requested: bool = False
    shutdown_reason: str = ''
    pending_user_messages: List[TeammateMessage] = field(default_factory=list)
    total_permission_wait_ms: int = 0
    # Messages accumulated so far in this run
    messages: List[Any] = field(default_factory=list)
    # Model overrides from leader
    model_override: Optional[str] = None


# ---------------------------------------------------------------------------
# Teammate message injection
# ---------------------------------------------------------------------------

def inject_user_message_to_teammate(
    state: InProcessRunnerState,
    text: str,
) -> None:
    """
    Inject a user message (from the leader) into the teammate's message queue.
    This will be consumed as a 'user' turn when the teammate next needs input.
    """
    msg = TeammateMessage(
        role='user',
        content=text,
        text=text,
        is_injected=True,
    )
    state.pending_user_messages.append(msg)
    log_for_debugging(
        f'[swarm:inprocess] Injected user message into {state.teammate_name}: '
        f'{text[:80]}{"..." if len(text) > 80 else ""}'
    )


def pop_next_user_message(state: InProcessRunnerState) -> Optional[TeammateMessage]:
    """Pop the next pending user message from the queue."""
    if state.pending_user_messages:
        return state.pending_user_messages.pop(0)
    return None


# ---------------------------------------------------------------------------
# Shutdown handling
# ---------------------------------------------------------------------------

def request_teammate_shutdown(
    state: InProcessRunnerState,
    reason: str = 'Shutdown requested',
) -> None:
    """
    Signal that the teammate should shut down at its next opportunity.
    """
    if not state.shutdown_requested:
        state.shutdown_requested = True
        state.shutdown_reason = reason
        log_for_debugging(
            f'[swarm:inprocess] Shutdown requested for {state.teammate_name}: {reason}'
        )
        state.permission_bridge.reject_all(reason)


def handle_incoming_leader_message(
    state: InProcessRunnerState,
    message_text: str,
) -> bool:
    """
    Process a message from the leader. Returns True if it was a shutdown request.
    """
    shutdown = parse_shutdown_request(message_text)
    if shutdown:
        request_teammate_shutdown(state, shutdown['reason'])
        return True
    # Regular message — inject as user turn
    inject_user_message_to_teammate(state, message_text)
    return False


# ---------------------------------------------------------------------------
# Model override
# ---------------------------------------------------------------------------

def apply_model_override(
    state: InProcessRunnerState,
    model: Optional[str],
) -> None:
    """Apply a model override received from the leader."""
    if model and model != state.model_override:
        log_for_debugging(
            f'[swarm:inprocess] Model override for {state.teammate_name}: {model}'
        )
        state.model_override = model


# ---------------------------------------------------------------------------
# Permission wait tracking
# ---------------------------------------------------------------------------

class PermissionWaitTimer:
    """Context manager that tracks time spent waiting for permissions."""

    def __init__(self, state: InProcessRunnerState) -> None:
        self.state = state
        self._start: Optional[float] = None

    def __enter__(self) -> 'PermissionWaitTimer':
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        if self._start is not None:
            elapsed_ms = int((time.monotonic() - self._start) * 1000)
            self.state.total_permission_wait_ms += elapsed_ms
            log_for_debugging(
                f'[swarm:inprocess] Permission wait: {elapsed_ms}ms '
                f'(total: {self.state.total_permission_wait_ms}ms)'
            )
            self._start = None


# ---------------------------------------------------------------------------
# Leader permission bridge callbacks
# ---------------------------------------------------------------------------

def build_permission_context(
    state: InProcessRunnerState,
    on_permission_request: Optional[Callable[[PermissionRequest], None]] = None,
    on_permission_response_available: Optional[Callable[[str, PermissionResponse], None]] = None,
) -> Dict[str, Any]:
    """
    Build a dict of permission-related callbacks for the agent runtime.
    These are injected into the agent's tool-use context.
    """
    async def check_tool_permission(
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Returns (approved, denial_reason).
        Called by the agent before executing a tool.
        """
        if on_permission_request is None:
            return True, None

        request_id = state.permission_bridge.make_request_id()
        with PermissionWaitTimer(state):
            response = await state.permission_bridge.request_permission(
                request_id=request_id,
                tool_name=tool_name,
                tool_input=tool_input,
                teammate_name=state.teammate_name,
                on_request=on_permission_request,
            )
        return response.get('approved', False), response.get('denial_reason')

    return {
        'check_tool_permission': check_tool_permission,
        'resolve_permission': state.permission_bridge.resolve_permission,
    }


# ---------------------------------------------------------------------------
# Content replacement state (for teammate message sanitization)
# ---------------------------------------------------------------------------

@dataclass
class ContentReplacementState:
    """
    Tracks content replacements applied to teammate messages.
    Used to rewrite or redact certain content for the leader.
    """
    replacements: Dict[str, str] = field(default_factory=dict)

    def add(self, original: str, replacement: str) -> None:
        self.replacements[original] = replacement

    def apply(self, text: str) -> str:
        for original, replacement in self.replacements.items():
            text = text.replace(original, replacement)
        return text


# ---------------------------------------------------------------------------
# Run result construction
# ---------------------------------------------------------------------------

def build_runner_result(
    state: InProcessRunnerState,
    success: bool,
    output: str = '',
    error: Optional[str] = None,
    stop_reason: str = 'end_turn',
) -> InProcessRunnerResult:
    """Construct a standardized result from a runner run."""
    return InProcessRunnerResult(
        success=success,
        output=output,
        error=error,
        messages=list(state.messages),
        stop_reason=stop_reason if not state.shutdown_requested else 'shutdown',
        permission_wait_ms=state.total_permission_wait_ms,
    )


# ---------------------------------------------------------------------------
# Main run function (facade — actual agent invocation is unported)
# ---------------------------------------------------------------------------

async def run_in_process_teammate(
    config: InProcessRunnerConfig,
    *,
    on_permission_request: Optional[Callable[[PermissionRequest], None]] = None,
    on_message: Optional[Callable[[Any], None]] = None,
    abort_signal: Optional[asyncio.Event] = None,
) -> InProcessRunnerResult:
    """
    Run a teammate in-process.

    This is the main entry point. In the full implementation, it calls
    runAgent() from the agent runtime. Since the agent runtime is not
    yet ported, this provides the surrounding infrastructure.

    Args:
        config: Configuration for the teammate run.
        on_permission_request: Callback when the teammate requests a tool permission.
        on_message: Callback for each message produced by the teammate.
        abort_signal: Optional asyncio.Event to signal early termination.
    Returns:
        InProcessRunnerResult
    """
    teammate_name = config.get('teammate_name', 'unnamed-teammate')
    log_for_debugging(f'[swarm:inprocess] Starting teammate: {teammate_name}')

    state = InProcessRunnerState(
        teammate_name=teammate_name,
        config=config,
    )

    try:
        # In a full implementation, this is where we call runAgent().
        # The actual agent execution loop is handled by the (unported) agent
        # runtime. For now, we provide the infrastructure and raise to signal
        # callers that the agent runtime needs to be connected.
        raise NotImplementedError(
            'In-process teammate runner requires the agent runtime (runAgent) '
            'which has not yet been ported. '
            'Use the subprocess-based runner for now.'
        )
    except NotImplementedError:
        return build_runner_result(
            state,
            success=False,
            error='Agent runtime not available for in-process execution',
            stop_reason='error',
        )
    except Exception as exc:
        log_for_debugging(f'[swarm:inprocess] Teammate {teammate_name} failed: {exc}')
        return build_runner_result(
            state,
            success=False,
            error=str(exc),
            stop_reason='error',
        )
    finally:
        state.permission_bridge.reject_all('Teammate run ended')
        log_for_debugging(f'[swarm:inprocess] Teammate {teammate_name} finished')


# ---------------------------------------------------------------------------
# Append teammate message (used by team coordinator)
# ---------------------------------------------------------------------------

def append_teammate_message(
    state: InProcessRunnerState,
    message: Any,
) -> None:
    """Append a message to the teammate's message history."""
    state.messages.append(message)


# ---------------------------------------------------------------------------
# Task list utilities (used by swarm coordinator)
# ---------------------------------------------------------------------------

def get_incomplete_tasks(tasks: List[SwarmTask]) -> List[SwarmTask]:
    """Return tasks that are not completed or failed."""
    return [t for t in tasks if t.status not in ('completed', 'failed')]


def get_failed_tasks(tasks: List[SwarmTask]) -> List[SwarmTask]:
    return [t for t in tasks if t.status == 'failed']


def all_tasks_done(tasks: List[SwarmTask]) -> bool:
    return all(t.status in ('completed', 'failed') for t in tasks)


def mark_task_started(task: SwarmTask) -> None:
    task.status = 'in_progress'
    task.started_at = time.time()


def mark_task_completed(task: SwarmTask, result: str) -> None:
    task.status = 'completed'
    task.result = result
    task.completed_at = time.time()


def mark_task_failed(task: SwarmTask, error: str) -> None:
    task.status = 'failed'
    task.error = error
    task.completed_at = time.time()
