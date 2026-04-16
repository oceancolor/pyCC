# 原始 TS: bridge/bridgeMain.ts
"""
Bridge main loop and CLI entry point for Claude Code Remote Control.

Ported from bridgeMain.ts (2999 lines). Handles:
- Poll loop for fetching work from bridge server
- Session spawning, lifecycle management, worktree creation/cleanup
- Heartbeat logic, backoff/retry, sleep detection
- CLI arg parsing (parseArgs / bridgeMain)
- Headless bridge entrypoint (runBridgeHeadless)
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import re
import signal as signal_module
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Literal, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type stubs / fallback imports for symbols that may not yet be in types.py
# ---------------------------------------------------------------------------

try:
    from .types import (  # type: ignore[attr-defined]
        BRIDGE_LOGIN_ERROR,
        BridgeApiClient,
        BridgeConfig,
        DEFAULT_SESSION_TIMEOUT_MS,
    )
except ImportError:
    BRIDGE_LOGIN_ERROR = (  # type: ignore[assignment]
        "Error: You must be logged in to use Remote Control.\n\n"
        "Remote Control is only available with claude.ai subscriptions. "
        "Please use `/login` to sign in with your claude.ai account."
    )
    DEFAULT_SESSION_TIMEOUT_MS = 24 * 60 * 60 * 1000  # type: ignore[assignment]

    class BridgeConfig:  # type: ignore[no-redef]
        """Runtime configuration for a bridge connection."""

        def __init__(
            self, base_url: str = "", access_token: str | None = None, **kw: Any
        ) -> None:
            self.base_url = base_url
            self.access_token = access_token
            for k, v in kw.items():
                setattr(self, k, v)

    class BridgeApiClient:  # type: ignore[no-redef]
        """Abstract interface for bridge API operations."""


# SpawnMode, SessionHandle, SessionSpawner, SessionSpawnOpts, SessionDoneStatus,
# and BridgeLogger are defined below since they are not yet in types.py.

SpawnMode = Literal["single-session", "same-dir", "worktree"]
SessionDoneStatus = Literal["completed", "failed", "interrupted"]


class SessionHandle:
    """Abstract handle for a running Claude session child process."""

    @property
    def done(self) -> asyncio.Future:
        """Future that resolves to SessionDoneStatus when the session exits."""
        raise NotImplementedError

    @property
    def current_activity(self) -> dict[str, Any] | None:
        return None

    @property
    def activities(self) -> list[dict[str, Any]]:
        return []

    @property
    def last_stderr(self) -> list[str]:
        return []

    def kill(self) -> None:
        raise NotImplementedError

    def force_kill(self) -> None:
        raise NotImplementedError

    def update_access_token(self, token: str) -> None:
        pass


@dataclass
class SessionSpawnOpts:
    """Options passed to SessionSpawner.spawn()."""

    session_id: str
    sdk_url: str
    access_token: str
    use_ccr_v2: bool = False
    worker_epoch: int | None = None
    on_first_user_message: Callable[[str], None] | None = None


class SessionSpawner:
    """Abstract factory for spawning Claude sessions."""

    def spawn(self, opts: SessionSpawnOpts, directory: str) -> SessionHandle:
        raise NotImplementedError


class BridgeLogger:
    """Abstract logger interface for bridge TUI / headless output."""

    def print_banner(self, cfg: Any, env_id: str) -> None:
        pass

    def log_session_start(self, sid: str, prompt: str) -> None:
        pass

    def log_session_complete(self, sid: str, ms: int) -> None:
        pass

    def log_session_failed(self, sid: str, err: str) -> None:
        pass

    def log_status(self, s: str) -> None:
        pass

    def log_verbose(self, s: str) -> None:
        pass

    def log_error(self, s: str) -> None:
        pass

    def log_reconnected(self, ms: int) -> None:
        pass

    def add_session(self, sid: str, url: str) -> None:
        pass

    def remove_session(self, sid: str) -> None:
        pass

    def update_idle_status(self) -> None:
        pass

    def update_reconnecting_status(self, delay: str, elapsed: str) -> None:
        pass

    def update_session_status(self, *args: Any) -> None:
        pass

    def update_session_activity(self, *args: Any) -> None:
        pass

    def update_session_count(self, *args: Any) -> None:
        pass

    def update_failed_status(self, *args: Any) -> None:
        pass

    def set_spawn_mode_display(self, *args: Any) -> None:
        pass

    def set_repo_info(self, *args: Any) -> None:
        pass

    def set_debug_log_path(self, *args: Any) -> None:
        pass

    def set_attached(self, *args: Any) -> None:
        pass

    def set_session_title(self, *args: Any) -> None:
        pass

    def clear_status(self) -> None:
        pass

    def toggle_qr(self) -> None:
        pass

    def refresh_display(self) -> None:
        pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATUS_UPDATE_INTERVAL_S: float = 1.0
SPAWN_SESSIONS_DEFAULT: int = 32

# ---------------------------------------------------------------------------
# BackoffConfig
# ---------------------------------------------------------------------------


@dataclass
class BackoffConfig:
    """Exponential backoff configuration for the bridge poll loop."""

    conn_initial_ms: int = 2_000
    conn_cap_ms: int = 120_000       # 2 minutes
    conn_give_up_ms: int = 600_000   # 10 minutes
    general_initial_ms: int = 500
    general_cap_ms: int = 30_000
    general_give_up_ms: int = 600_000  # 10 minutes
    # SIGTERM → SIGKILL grace period. Default 30s.
    shutdown_grace_ms: int = 30_000
    # stopWorkWithRetry base delay (1s/2s/4s backoff). Default 1000ms.
    stop_work_base_delay_ms: int = 1_000


DEFAULT_BACKOFF = BackoffConfig()

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _add_jitter(ms: float) -> float:
    """Add ±25% jitter to a delay value."""
    return max(0.0, ms + ms * 0.25 * (2 * random.random() - 1))


def _format_delay(ms: float) -> str:
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{round(ms)}ms"


def _poll_sleep_detection_threshold_ms(backoff: BackoffConfig) -> float:
    """
    Returns the threshold for detecting system sleep/wake in the poll loop.
    Must exceed the max backoff cap — otherwise normal backoff delays trigger
    false sleep detection. Using 2× the connection backoff cap.
    """
    return backoff.conn_cap_ms * 2


def is_connection_error(err: BaseException) -> bool:
    """Return True for network-level connection errors."""
    code = getattr(err, "code", None) or getattr(err, "errno", None)
    if isinstance(code, str):
        return code in {
            "ECONNREFUSED",
            "ECONNRESET",
            "ETIMEDOUT",
            "ENETUNREACH",
            "EHOSTUNREACH",
        }
    if isinstance(code, int):
        import errno as _errno
        return code in {
            _errno.ECONNREFUSED,
            _errno.ECONNRESET,
            _errno.ETIMEDOUT,
            _errno.ENETUNREACH,
            _errno.EHOSTUNREACH,
        }
    # Also catch common aiohttp / requests connection errors
    name = type(err).__name__
    return any(
        kw in name
        for kw in ("ConnectionRefused", "ConnectionReset", "Timeout", "NetworkUnreachable")
    )


def is_server_error(err: BaseException) -> bool:
    """Return True for HTTP 5xx errors (akin to axios ERR_BAD_RESPONSE)."""
    code = getattr(err, "code", None)
    if isinstance(code, str) and code == "ERR_BAD_RESPONSE":
        return True
    status = getattr(err, "status", None) or getattr(err, "status_code", None)
    if isinstance(status, int) and 500 <= status < 600:
        return True
    return False


def _derive_session_title(text: str) -> str:
    """Derive a session title from a user message: first line, truncated."""
    TITLE_MAX_LEN = 80
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= TITLE_MAX_LEN:
        return flat
    return flat[: TITLE_MAX_LEN - 3] + "..."


# ---------------------------------------------------------------------------
# Stub helpers for external dependencies (analytics, debug logging, etc.)
# These wrap functionality that is Bun/Node-specific in the original.
# ---------------------------------------------------------------------------


def _log_event(event_name: str, props: dict[str, Any] | None = None) -> None:
    """Fire-and-forget analytics event (no-op stub)."""
    logger.debug("analytics event: %s %s", event_name, props or {})


def _log_for_debugging(msg: str, *, level: str = "debug") -> None:
    """Debug/diagnostic log (routes to Python logger)."""
    log_fn = getattr(logger, level, logger.debug)
    log_fn(msg)


def _log_for_diagnostics(
    severity: str, event_name: str, props: dict[str, Any]
) -> None:
    logger.info("[diag:%s] %s %s", severity, event_name, props)


def _error_message(err: BaseException | Any) -> str:
    return str(err)


def _format_duration_ms(ms: float) -> str:
    """Format milliseconds as human-readable duration."""
    s = int(ms / 1000)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


# ---------------------------------------------------------------------------
# Sentinel exception types (mirrors BridgeFatalError from bridgeApi.ts)
# ---------------------------------------------------------------------------


class BridgeFatalError(Exception):
    """Fatal bridge API error — no point retrying."""

    def __init__(
        self,
        message: str,
        status: int | None = None,
        error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error_type = error_type


def is_expired_error_type(error_type: str | None) -> bool:
    return error_type in {"environment_expired", "environment_deleted"}


def is_suppressible_403(err: BridgeFatalError) -> bool:
    return err.status == 403 and err.error_type in {
        "external_poll_sessions",
        "environments_manage",
    }


# ---------------------------------------------------------------------------
# CapacityWake — interrupt at-capacity sleep when a session ends
# ---------------------------------------------------------------------------


class _CapacityWake:
    """
    Signal to wake an at-capacity sleep early when a session completes,
    so the bridge can immediately accept new work.
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def wake(self) -> None:
        self._event.set()

    def signal(self) -> asyncio.Event:
        """Return a fresh event that fires on the next wake() call."""
        self._event.clear()
        return self._event

    async def wait(self, timeout_s: float | None = None) -> None:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            pass
        finally:
            self._event.clear()


# ---------------------------------------------------------------------------
# Retry helper: stopWorkWithRetry
# ---------------------------------------------------------------------------


async def stop_work_with_retry(
    api: BridgeApiClient,
    environment_id: str,
    work_id: str,
    bridge_logger: BridgeLogger,
    base_delay_ms: int = 1_000,
) -> None:
    """
    Retry stopWork with exponential backoff (3 attempts, 1s/2s/4s).
    Ensures the server learns the work item ended, preventing server-side zombies.
    """
    MAX_ATTEMPTS = 3
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await api.stop_work(environment_id, work_id, False)
            _log_for_debugging(
                f"[bridge:work] stopWork succeeded for workId={work_id} on attempt {attempt}/{MAX_ATTEMPTS}"
            )
            return
        except BridgeFatalError as err:
            if is_suppressible_403(err):
                _log_for_debugging(
                    f"[bridge:work] Suppressed stopWork 403 for {work_id}: {err}"
                )
            else:
                bridge_logger.log_error(f"Failed to stop work {work_id}: {err}")
            _log_for_diagnostics(
                "error", "bridge_stop_work_failed", {"attempts": attempt, "fatal": True}
            )
            return
        except Exception as err:
            err_msg = _error_message(err)
            if attempt < MAX_ATTEMPTS:
                delay = _add_jitter(base_delay_ms * (2 ** (attempt - 1)))
                bridge_logger.log_verbose(
                    f"Failed to stop work {work_id} (attempt {attempt}/{MAX_ATTEMPTS}), "
                    f"retrying in {_format_delay(delay)}: {err_msg}"
                )
                await asyncio.sleep(delay / 1000)
            else:
                bridge_logger.log_error(
                    f"Failed to stop work {work_id} after {MAX_ATTEMPTS} attempts: {err_msg}"
                )
                _log_for_diagnostics(
                    "error", "bridge_stop_work_failed", {"attempts": MAX_ATTEMPTS}
                )


# ---------------------------------------------------------------------------
# Session timeout handler
# ---------------------------------------------------------------------------


def _on_session_timeout(
    session_id: str,
    timeout_ms: int,
    bridge_logger: BridgeLogger,
    timed_out_sessions: set[str],
    handle: SessionHandle,
) -> None:
    _log_for_debugging(
        f"[bridge:session] sessionId={session_id} timed out after "
        f"{_format_duration_ms(timeout_ms)}"
    )
    _log_event("tengu_bridge_session_timeout", {"timeout_ms": timeout_ms})
    bridge_logger.log_session_failed(
        session_id, f"Session timed out after {_format_duration_ms(timeout_ms)}"
    )
    timed_out_sessions.add(session_id)
    handle.kill()


# ---------------------------------------------------------------------------
# Compat session ID conversion stubs
# ---------------------------------------------------------------------------


def _to_compat_session_id(session_id: str) -> str:
    """Convert infra-layer session_id to compat-surface form (session_*)."""
    if session_id.startswith("cse_"):
        return "session_" + session_id[4:]
    return session_id


def _to_infra_session_id(session_id: str) -> str:
    """Convert compat-surface session_* to infra cse_* form."""
    if session_id.startswith("session_"):
        return "cse_" + session_id[8:]
    return session_id


def _same_session_id(a: str, b: str) -> bool:
    return _to_compat_session_id(a) == _to_compat_session_id(b)


# ---------------------------------------------------------------------------
# Safe spawn wrapper
# ---------------------------------------------------------------------------


def _safe_spawn(
    spawner: SessionSpawner,
    opts: SessionSpawnOpts,
    directory: str,
) -> "SessionHandle | str":
    """Attempt to spawn a session; returns error string if spawn throws."""
    try:
        return spawner.spawn(opts, directory)
    except Exception as err:
        err_msg = _error_message(err)
        logger.error("Session spawn failed: %s", err_msg)
        return err_msg


# ---------------------------------------------------------------------------
# runBridgeLoop — main poll loop
# ---------------------------------------------------------------------------


async def run_bridge_loop(
    config: BridgeConfig,
    environment_id: str,
    environment_secret: str,
    api: BridgeApiClient,
    spawner: SessionSpawner,
    bridge_logger: BridgeLogger,
    abort_event: asyncio.Event,
    backoff_config: BackoffConfig | None = None,
    initial_session_id: str | None = None,
    get_access_token: Callable[[], Coroutine[Any, Any, str | None]] | None = None,
) -> None:
    """
    Main bridge poll loop.

    Polls the bridge server for work, spawns sessions, manages their
    lifecycle, and handles reconnection backoff.

    Args:
        config: Bridge runtime configuration.
        environment_id: The registered environment UUID.
        environment_secret: Shared secret for polling.
        api: HTTP client for bridge API calls.
        spawner: Factory for spawning child Claude sessions.
        bridge_logger: Live-display logger for the bridge TUI.
        abort_event: Set this event to stop the loop.
        backoff_config: Optional backoff tuning (defaults to DEFAULT_BACKOFF).
        initial_session_id: Pre-created session to show in UI before first poll.
        get_access_token: Async callable returning current OAuth token.
    """
    if backoff_config is None:
        backoff_config = DEFAULT_BACKOFF

    # Local stop event so onSessionDone can stop the loop.
    # Also responds to abort_event.
    loop_stop = asyncio.Event()

    async def _wait_for_stop() -> None:
        await abort_event.wait()
        loop_stop.set()

    stop_task = asyncio.create_task(_wait_for_stop())

    # ----- Session tracking -----
    active_sessions: dict[str, SessionHandle] = {}
    session_start_times: dict[str, float] = {}
    session_work_ids: dict[str, str] = {}
    session_compat_ids: dict[str, str] = {}
    session_ingress_tokens: dict[str, str] = {}
    session_timers: dict[str, asyncio.TimerHandle] = {}
    completed_work_ids: set[str] = set()
    session_worktrees: dict[
        str,
        dict[str, Any],
    ] = {}
    timed_out_sessions: set[str] = set()
    titled_sessions: set[str] = set()
    v2_sessions: set[str] = set()
    capacity_wake = _CapacityWake()

    # Track in-flight cleanup coroutines
    pending_cleanups: set[asyncio.Task] = set()

    def _track_cleanup(coro: Coroutine) -> None:
        t = asyncio.create_task(coro)
        pending_cleanups.add(t)
        t.add_done_callback(pending_cleanups.discard)

    # ----- Backoff / error state -----
    conn_backoff: float = 0.0
    general_backoff: float = 0.0
    conn_error_start: float | None = None
    general_error_start: float | None = None
    last_poll_error_time: float | None = None
    fatal_exit = False

    # ----- Status update -----
    status_update_task: asyncio.Task | None = None
    loop = asyncio.get_event_loop()

    def _update_status_display() -> None:
        bridge_logger.update_session_count(
            len(active_sessions), config.max_sessions, config.spawn_mode
        )
        for sid, handle in active_sessions.items():
            act = handle.current_activity
            if act:
                bridge_logger.update_session_activity(
                    session_compat_ids.get(sid, sid), act
                )
        if not active_sessions:
            bridge_logger.update_idle_status()
            return
        session_id, handle = list(active_sessions.items())[-1]
        start_time = session_start_times.get(session_id)
        if not start_time:
            return
        activity = handle.current_activity
        if not activity or activity.get("type") in ("result", "error"):
            if config.max_sessions > 1:
                bridge_logger.refresh_display()
            return
        elapsed = _format_duration_ms((loop.time() * 1000) - start_time * 1000)
        trail = [
            a.get("summary", "")
            for a in handle.activities
            if a.get("type") == "tool_start"
        ][-5:]
        bridge_logger.update_session_status(session_id, elapsed, activity, trail)

    async def _status_update_loop() -> None:
        while not loop_stop.is_set():
            _update_status_display()
            try:
                await asyncio.wait_for(loop_stop.wait(), timeout=STATUS_UPDATE_INTERVAL_S)
            except asyncio.TimeoutError:
                pass

    def _start_status_updates() -> None:
        nonlocal status_update_task
        _stop_status_updates()
        _update_status_display()
        status_update_task = asyncio.create_task(_status_update_loop())

    def _stop_status_updates() -> None:
        nonlocal status_update_task
        if status_update_task and not status_update_task.done():
            status_update_task.cancel()
        status_update_task = None

    # ----- Heartbeat -----
    async def _heartbeat_active_work_items() -> Literal["ok", "auth_failed", "fatal", "failed"]:
        any_success = False
        any_fatal = False
        auth_failed_sessions: list[str] = []
        for session_id in list(active_sessions):
            work_id = session_work_ids.get(session_id)
            ingress_token = session_ingress_tokens.get(session_id)
            if not work_id or not ingress_token:
                continue
            try:
                await api.heartbeat_work(environment_id, work_id, ingress_token)
                any_success = True
            except BridgeFatalError as err:
                _log_for_debugging(
                    f"[bridge:heartbeat] Failed for sessionId={session_id} workId={work_id}: {err}"
                )
                _log_event(
                    "tengu_bridge_heartbeat_error",
                    {
                        "status": err.status,
                        "error_type": (
                            "auth_failed" if err.status in (401, 403) else "fatal"
                        ),
                    },
                )
                if err.status in (401, 403):
                    auth_failed_sessions.append(session_id)
                else:
                    any_fatal = True
            except Exception as err:
                _log_for_debugging(
                    f"[bridge:heartbeat] Failed for sessionId={session_id} workId={work_id}: {err}"
                )

        for session_id in auth_failed_sessions:
            bridge_logger.log_verbose(
                f"Session {session_id} token expired — re-queuing via bridge/reconnect"
            )
            try:
                await api.reconnect_session(environment_id, session_id)
                _log_for_debugging(
                    f"[bridge:heartbeat] Re-queued sessionId={session_id} via bridge/reconnect"
                )
            except Exception as err:
                bridge_logger.log_error(
                    f"Failed to refresh session {session_id} token: {_error_message(err)}"
                )

        if any_fatal:
            return "fatal"
        if auth_failed_sessions:
            return "auth_failed"
        return "ok" if any_success else "failed"

    # ----- onSessionDone -----
    def _on_session_done(
        session_id: str,
        start_time: float,
        handle: SessionHandle,
    ) -> Callable[[SessionDoneStatus], None]:
        def _callback(raw_status: SessionDoneStatus) -> None:
            nonlocal fatal_exit
            work_id = session_work_ids.get(session_id)
            active_sessions.pop(session_id, None)
            session_start_times.pop(session_id, None)
            session_work_ids.pop(session_id, None)
            session_ingress_tokens.pop(session_id, None)
            compat_id = session_compat_ids.pop(session_id, session_id)
            bridge_logger.remove_session(compat_id)
            titled_sessions.discard(compat_id)
            v2_sessions.discard(session_id)

            timer = session_timers.pop(session_id, None)
            if timer:
                timer.cancel()

            capacity_wake.wake()

            was_timed_out = session_id in timed_out_sessions
            timed_out_sessions.discard(session_id)
            status: SessionDoneStatus = (
                "failed" if was_timed_out and raw_status == "interrupted" else raw_status
            )
            duration_ms = (loop.time() - start_time) * 1000

            _log_for_debugging(
                f"[bridge:session] sessionId={session_id} workId={work_id or 'unknown'} "
                f"exited status={status} duration={_format_duration_ms(duration_ms)}"
            )
            _log_event(
                "tengu_bridge_session_done",
                {"status": status, "duration_ms": duration_ms},
            )
            _log_for_diagnostics(
                "info", "bridge_session_done", {"status": status, "duration_ms": duration_ms}
            )

            bridge_logger.clear_status()
            _stop_status_updates()

            stderr_summary = (
                "\n".join(handle.last_stderr) if handle.last_stderr else None
            )

            if status == "completed":
                bridge_logger.log_session_complete(session_id, int(duration_ms))
            elif status == "failed":
                if not was_timed_out and not loop_stop.is_set():
                    failure_message = stderr_summary or "Process exited with error"
                    bridge_logger.log_session_failed(session_id, failure_message)
                    logger.error("Bridge session failed: %s", failure_message)
            elif status == "interrupted":
                bridge_logger.log_verbose(f"Session {session_id} interrupted")

            if status != "interrupted" and work_id:
                _track_cleanup(
                    stop_work_with_retry(
                        api,
                        environment_id,
                        work_id,
                        bridge_logger,
                        backoff_config.stop_work_base_delay_ms,
                    )
                )
                completed_work_ids.add(work_id)

            wt = session_worktrees.pop(session_id, None)
            if wt:
                async def _remove_wt(w: dict) -> None:
                    try:
                        await api.remove_agent_worktree(
                            w["worktree_path"],
                            w.get("worktree_branch"),
                            w.get("git_root"),
                            w.get("hook_based"),
                        )
                    except Exception as e:
                        bridge_logger.log_verbose(
                            f"Failed to remove worktree {w['worktree_path']}: {e}"
                        )

                _track_cleanup(_remove_wt(wt))

            if status != "interrupted" and not loop_stop.is_set():
                if config.spawn_mode != "single-session":
                    async def _archive(cid: str) -> None:
                        try:
                            await api.archive_session(cid)
                        except Exception as e:
                            bridge_logger.log_verbose(
                                f"Failed to archive session {session_id}: {e}"
                            )

                    _track_cleanup(_archive(compat_id))
                    _log_for_debugging(
                        f"[bridge:session] Session {status}, returning to idle (multi-session mode)"
                    )
                else:
                    _log_for_debugging(
                        f"[bridge:session] Session {status}, aborting poll loop to tear down environment"
                    )
                    loop_stop.set()
                    return

            if not loop_stop.is_set():
                _start_status_updates()

        return _callback

    # ----- Initial setup -----
    _log_for_debugging(
        f"[bridge:work] Starting poll loop spawnMode={config.spawn_mode} "
        f"maxSessions={config.max_sessions} environmentId={environment_id}"
    )
    _log_for_diagnostics(
        "info",
        "bridge_loop_started",
        {"max_sessions": config.max_sessions, "spawn_mode": config.spawn_mode},
    )

    bridge_logger.update_session_count(0, config.max_sessions, config.spawn_mode)

    if initial_session_id:
        bridge_logger.set_attached(initial_session_id)

    if not initial_session_id:
        _start_status_updates()

    loop_start_time = loop.time()

    # ----- Main poll loop -----
    try:
        while not loop_stop.is_set():
            # poll_config is a stub; for Python we use simple fixed intervals
            poll_config = _get_poll_interval_config()

            try:
                work = await api.poll_for_work(
                    environment_id,
                    environment_secret,
                    loop_stop,
                    poll_config["reclaim_older_than_ms"],
                )

                was_disconnected = (
                    conn_error_start is not None or general_error_start is not None
                )
                if was_disconnected:
                    disconnected_ms = (
                        loop.time() * 1000
                        - (conn_error_start or general_error_start or loop.time()) * 1000
                    )
                    bridge_logger.log_reconnected(int(disconnected_ms))
                    _log_for_debugging(
                        f"[bridge:poll] Reconnected after {_format_duration_ms(disconnected_ms)}"
                    )
                    _log_event(
                        "tengu_bridge_reconnected", {"disconnected_ms": disconnected_ms}
                    )

                conn_backoff = 0.0
                general_backoff = 0.0
                conn_error_start = None
                general_error_start = None
                last_poll_error_time = None

                if work is None:
                    at_cap = len(active_sessions) >= config.max_sessions
                    if at_cap:
                        at_cap_ms = poll_config["multisession_poll_interval_ms_at_capacity"]
                        hb_interval_ms = poll_config["non_exclusive_heartbeat_interval_ms"]

                        if hb_interval_ms > 0:
                            _log_event(
                                "tengu_bridge_heartbeat_mode_entered",
                                {
                                    "active_sessions": len(active_sessions),
                                    "heartbeat_interval_ms": hb_interval_ms,
                                },
                            )
                            poll_deadline = (
                                loop.time() * 1000 + at_cap_ms if at_cap_ms > 0 else None
                            )
                            hb_result: str = "ok"
                            hb_cycles = 0

                            while (
                                not loop_stop.is_set()
                                and len(active_sessions) >= config.max_sessions
                                and (
                                    poll_deadline is None
                                    or loop.time() * 1000 < poll_deadline
                                )
                            ):
                                hb_cfg = _get_poll_interval_config()
                                if hb_cfg["non_exclusive_heartbeat_interval_ms"] <= 0:
                                    break
                                hb_result = await _heartbeat_active_work_items()
                                if hb_result in ("auth_failed", "fatal"):
                                    break
                                hb_cycles += 1
                                try:
                                    await asyncio.wait_for(
                                        loop_stop.wait(),
                                        timeout=hb_cfg["non_exclusive_heartbeat_interval_ms"] / 1000,
                                    )
                                except asyncio.TimeoutError:
                                    pass

                            # exit reason telemetry
                            if hb_result in ("auth_failed", "fatal"):
                                exit_reason = hb_result
                            elif loop_stop.is_set():
                                exit_reason = "shutdown"
                            elif len(active_sessions) < config.max_sessions:
                                exit_reason = "capacity_changed"
                            elif (
                                poll_deadline is not None
                                and loop.time() * 1000 >= poll_deadline
                            ):
                                exit_reason = "poll_due"
                            else:
                                exit_reason = "config_disabled"

                            _log_event(
                                "tengu_bridge_heartbeat_mode_exited",
                                {
                                    "reason": exit_reason,
                                    "heartbeat_cycles": hb_cycles,
                                    "active_sessions": len(active_sessions),
                                },
                            )

                            if hb_result in ("auth_failed", "fatal"):
                                sleep_ms = at_cap_ms if at_cap_ms > 0 else hb_interval_ms
                                try:
                                    await asyncio.wait_for(
                                        loop_stop.wait(), timeout=sleep_ms / 1000
                                    )
                                except asyncio.TimeoutError:
                                    pass

                        elif at_cap_ms > 0:
                            try:
                                await asyncio.wait_for(
                                    loop_stop.wait(), timeout=at_cap_ms / 1000
                                )
                            except asyncio.TimeoutError:
                                pass
                    else:
                        if active_sessions:
                            interval = poll_config[
                                "multisession_poll_interval_ms_partial_capacity"
                            ]
                        else:
                            interval = poll_config[
                                "multisession_poll_interval_ms_not_at_capacity"
                            ]
                        try:
                            await asyncio.wait_for(
                                loop_stop.wait(), timeout=interval / 1000
                            )
                        except asyncio.TimeoutError:
                            pass
                    continue

                at_capacity_before_switch = len(active_sessions) >= config.max_sessions

                # Skip already-completed work
                if work.id in completed_work_ids:
                    _log_for_debugging(
                        f"[bridge:work] Skipping already-completed workId={work.id}"
                    )
                    if at_capacity_before_switch:
                        hb_ms = poll_config["non_exclusive_heartbeat_interval_ms"]
                        at_cap_ms = poll_config["multisession_poll_interval_ms_at_capacity"]
                        if hb_ms > 0:
                            await _heartbeat_active_work_items()
                            try:
                                await asyncio.wait_for(
                                    loop_stop.wait(), timeout=hb_ms / 1000
                                )
                            except asyncio.TimeoutError:
                                pass
                        elif at_cap_ms > 0:
                            try:
                                await asyncio.wait_for(
                                    loop_stop.wait(), timeout=at_cap_ms / 1000
                                )
                            except asyncio.TimeoutError:
                                pass
                    else:
                        try:
                            await asyncio.wait_for(loop_stop.wait(), timeout=1.0)
                        except asyncio.TimeoutError:
                            pass
                    continue

                # Decode work secret
                try:
                    secret = _decode_work_secret(work.secret)
                except Exception as err:
                    err_msg = _error_message(err)
                    bridge_logger.log_error(
                        f"Failed to decode work secret for workId={work.id}: {err_msg}"
                    )
                    _log_event("tengu_bridge_work_secret_failed", {})
                    completed_work_ids.add(work.id)
                    _track_cleanup(
                        stop_work_with_retry(
                            api,
                            environment_id,
                            work.id,
                            bridge_logger,
                            backoff_config.stop_work_base_delay_ms,
                        )
                    )
                    if at_capacity_before_switch:
                        hb_ms = poll_config["non_exclusive_heartbeat_interval_ms"]
                        at_cap_ms = poll_config["multisession_poll_interval_ms_at_capacity"]
                        if hb_ms > 0:
                            await _heartbeat_active_work_items()
                            try:
                                await asyncio.wait_for(
                                    loop_stop.wait(), timeout=hb_ms / 1000
                                )
                            except asyncio.TimeoutError:
                                pass
                        elif at_cap_ms > 0:
                            try:
                                await asyncio.wait_for(
                                    loop_stop.wait(), timeout=at_cap_ms / 1000
                                )
                            except asyncio.TimeoutError:
                                pass
                    continue

                # ack helper
                async def _ack_work() -> None:
                    _log_for_debugging(f"[bridge:work] Acknowledging workId={work.id}")
                    try:
                        await api.acknowledge_work(
                            environment_id,
                            work.id,
                            secret["session_ingress_token"],
                        )
                    except Exception as err:
                        _log_for_debugging(
                            f"[bridge:work] Acknowledge failed workId={work.id}: {_error_message(err)}"
                        )

                work_type = work.data.get("type") if isinstance(work.data, dict) else work.data.type

                if work_type == "healthcheck":
                    await _ack_work()
                    _log_for_debugging("[bridge:work] Healthcheck received")
                    bridge_logger.log_verbose("Healthcheck received")

                elif work_type == "session":
                    session_id = (
                        work.data["id"]
                        if isinstance(work.data, dict)
                        else work.data.id
                    )

                    # Validate session_id
                    if not _validate_bridge_id(session_id):
                        await _ack_work()
                        bridge_logger.log_error(
                            f"Invalid session_id received: {session_id}"
                        )
                        goto_capacity_throttle = at_capacity_before_switch
                        # fall through to capacity throttle below
                    else:
                        # Existing session: deliver fresh token
                        existing_handle = active_sessions.get(session_id)
                        if existing_handle:
                            existing_handle.update_access_token(
                                secret["session_ingress_token"]
                            )
                            session_ingress_tokens[session_id] = secret["session_ingress_token"]
                            session_work_ids[session_id] = work.id
                            _log_for_debugging(
                                f"[bridge:work] Updated access token for existing sessionId={session_id} workId={work.id}"
                            )
                            await _ack_work()
                            goto_capacity_throttle = at_capacity_before_switch
                        elif len(active_sessions) >= config.max_sessions:
                            _log_for_debugging(
                                f"[bridge:work] At capacity ({len(active_sessions)}/{config.max_sessions}), "
                                f"cannot spawn new session for workId={work.id}"
                            )
                            goto_capacity_throttle = at_capacity_before_switch
                        else:
                            goto_capacity_throttle = at_capacity_before_switch
                            await _ack_work()
                            spawn_start_time = loop.time()

                            # Determine SDK URL and CCR v2
                            use_ccr_v2 = False
                            worker_epoch: int | None = None
                            use_code_sessions = secret.get("use_code_sessions", False)

                            if use_code_sessions or os.environ.get(
                                "CLAUDE_BRIDGE_USE_CCR_V2", ""
                            ).lower() in ("1", "true", "yes"):
                                sdk_url = _build_ccr_v2_sdk_url(
                                    config.api_base_url, session_id
                                )
                                for attempt in range(1, 3):
                                    try:
                                        worker_epoch = await api.register_worker(
                                            sdk_url,
                                            secret["session_ingress_token"],
                                        )
                                        use_ccr_v2 = True
                                        _log_for_debugging(
                                            f"[bridge:session] CCR v2: registered worker "
                                            f"sessionId={session_id} epoch={worker_epoch} attempt={attempt}"
                                        )
                                        break
                                    except Exception as err:
                                        err_msg = _error_message(err)
                                        if attempt < 2:
                                            _log_for_debugging(
                                                f"[bridge:session] CCR v2: registerWorker attempt {attempt} "
                                                f"failed, retrying: {err_msg}"
                                            )
                                            try:
                                                await asyncio.wait_for(
                                                    loop_stop.wait(), timeout=2.0
                                                )
                                            except asyncio.TimeoutError:
                                                pass
                                            if loop_stop.is_set():
                                                break
                                        else:
                                            bridge_logger.log_error(
                                                f"CCR v2 worker registration failed for session "
                                                f"{session_id}: {err_msg}"
                                            )
                                            logger.error("registerWorker failed: %s", err_msg)
                                            completed_work_ids.add(work.id)
                                            _track_cleanup(
                                                stop_work_with_retry(
                                                    api,
                                                    environment_id,
                                                    work.id,
                                                    bridge_logger,
                                                    backoff_config.stop_work_base_delay_ms,
                                                )
                                            )
                                if not use_ccr_v2:
                                    # Skip to capacity throttle
                                    if at_capacity_before_switch:
                                        hb_ms = poll_config["non_exclusive_heartbeat_interval_ms"]
                                        at_cap_ms = poll_config[
                                            "multisession_poll_interval_ms_at_capacity"
                                        ]
                                        if hb_ms > 0:
                                            await _heartbeat_active_work_items()
                                            try:
                                                await asyncio.wait_for(
                                                    loop_stop.wait(), timeout=hb_ms / 1000
                                                )
                                            except asyncio.TimeoutError:
                                                pass
                                        elif at_cap_ms > 0:
                                            try:
                                                await asyncio.wait_for(
                                                    loop_stop.wait(), timeout=at_cap_ms / 1000
                                                )
                                            except asyncio.TimeoutError:
                                                pass
                                    continue
                            else:
                                sdk_url = _build_sdk_url(
                                    config.session_ingress_url, session_id
                                )

                            # Worktree creation
                            spawn_mode_at_decision = config.spawn_mode
                            session_dir = config.dir
                            worktree_create_ms = 0

                            if (
                                spawn_mode_at_decision == "worktree"
                                and (
                                    initial_session_id is None
                                    or not _same_session_id(session_id, initial_session_id)
                                )
                            ):
                                wt_start = loop.time()
                                try:
                                    wt = await api.create_agent_worktree(
                                        f"bridge-{_safe_filename_id(session_id)}"
                                    )
                                    worktree_create_ms = int(
                                        (loop.time() - wt_start) * 1000
                                    )
                                    session_worktrees[session_id] = {
                                        "worktree_path": wt["worktree_path"],
                                        "worktree_branch": wt.get("worktree_branch"),
                                        "git_root": wt.get("git_root"),
                                        "hook_based": wt.get("hook_based"),
                                    }
                                    session_dir = wt["worktree_path"]
                                    _log_for_debugging(
                                        f"[bridge:session] Created worktree for sessionId={session_id} "
                                        f"at {wt['worktree_path']}"
                                    )
                                except Exception as err:
                                    err_msg = _error_message(err)
                                    bridge_logger.log_error(
                                        f"Failed to create worktree for session {session_id}: {err_msg}"
                                    )
                                    logger.error("Worktree creation failed: %s", err_msg)
                                    completed_work_ids.add(work.id)
                                    _track_cleanup(
                                        stop_work_with_retry(
                                            api,
                                            environment_id,
                                            work.id,
                                            bridge_logger,
                                            backoff_config.stop_work_base_delay_ms,
                                        )
                                    )
                                    continue

                            _log_for_debugging(
                                f"[bridge:session] Spawning sessionId={session_id} sdkUrl={sdk_url}"
                            )

                            compat_session_id = _to_compat_session_id(session_id)

                            def _make_on_first_user_message(csid: str) -> Callable[[str], None]:
                                def _cb(text: str) -> None:
                                    if csid in titled_sessions:
                                        return
                                    titled_sessions.add(csid)
                                    title = _derive_session_title(text)
                                    bridge_logger.set_session_title(csid, title)
                                    _log_for_debugging(
                                        f"[bridge:title] derived title for {csid}: {title}"
                                    )

                                return _cb

                            spawn_opts = SessionSpawnOpts(
                                session_id=session_id,
                                sdk_url=sdk_url,
                                access_token=secret["session_ingress_token"],
                                use_ccr_v2=use_ccr_v2,
                                worker_epoch=worker_epoch,
                                on_first_user_message=_make_on_first_user_message(
                                    compat_session_id
                                ),
                            )

                            spawn_result = _safe_spawn(spawner, spawn_opts, session_dir)

                            if isinstance(spawn_result, str):
                                bridge_logger.log_error(
                                    f"Failed to spawn session {session_id}: {spawn_result}"
                                )
                                wt = session_worktrees.pop(session_id, None)
                                if wt:
                                    async def _remove_failed_wt(w: dict) -> None:
                                        try:
                                            await api.remove_agent_worktree(
                                                w["worktree_path"],
                                                w.get("worktree_branch"),
                                                w.get("git_root"),
                                                w.get("hook_based"),
                                            )
                                        except Exception as e:
                                            bridge_logger.log_verbose(
                                                f"Failed to remove worktree {w['worktree_path']}: {e}"
                                            )

                                    _track_cleanup(_remove_failed_wt(wt))
                                completed_work_ids.add(work.id)
                                _track_cleanup(
                                    stop_work_with_retry(
                                        api,
                                        environment_id,
                                        work.id,
                                        bridge_logger,
                                        backoff_config.stop_work_base_delay_ms,
                                    )
                                )
                            else:
                                handle = spawn_result
                                spawn_duration_ms = int(
                                    (loop.time() - spawn_start_time) * 1000
                                )
                                _log_event(
                                    "tengu_bridge_session_started",
                                    {
                                        "active_sessions": len(active_sessions),
                                        "spawn_mode": spawn_mode_at_decision,
                                        "in_worktree": session_id in session_worktrees,
                                        "spawn_duration_ms": spawn_duration_ms,
                                        "worktree_create_ms": worktree_create_ms,
                                    },
                                )
                                _log_for_diagnostics(
                                    "info",
                                    "bridge_session_started",
                                    {
                                        "spawn_mode": spawn_mode_at_decision,
                                        "in_worktree": session_id in session_worktrees,
                                        "spawn_duration_ms": spawn_duration_ms,
                                        "worktree_create_ms": worktree_create_ms,
                                    },
                                )

                                active_sessions[session_id] = handle
                                session_work_ids[session_id] = work.id
                                session_ingress_tokens[session_id] = secret[
                                    "session_ingress_token"
                                ]
                                session_compat_ids[session_id] = compat_session_id

                                start_time = loop.time()
                                session_start_times[session_id] = start_time

                                bridge_logger.log_session_start(
                                    session_id, f"Session {session_id}"
                                )

                                bridge_logger.add_session(
                                    compat_session_id,
                                    _get_remote_session_url(
                                        compat_session_id, config.session_ingress_url
                                    ),
                                )

                                _start_status_updates()
                                bridge_logger.set_attached(compat_session_id)

                                # Per-session timeout watchdog
                                timeout_ms = (
                                    config.session_timeout_ms
                                    if config.session_timeout_ms is not None
                                    else DEFAULT_SESSION_TIMEOUT_MS
                                )
                                if timeout_ms > 0:
                                    t = loop.call_later(
                                        timeout_ms / 1000,
                                        _on_session_timeout,
                                        session_id,
                                        timeout_ms,
                                        bridge_logger,
                                        timed_out_sessions,
                                        handle,
                                    )
                                    session_timers[session_id] = t

                                if use_ccr_v2:
                                    v2_sessions.add(session_id)

                                # Wire up session done callback
                                done_cb = _on_session_done(session_id, start_time, handle)
                                asyncio.ensure_future(
                                    _await_handle_done(handle, done_cb)
                                )

                else:
                    await _ack_work()
                    _log_for_debugging(
                        f"[bridge:work] Unknown work type: {work_type}, skipping"
                    )

                # At-capacity throttle after switch
                if at_capacity_before_switch:
                    hb_ms = poll_config["non_exclusive_heartbeat_interval_ms"]
                    at_cap_ms = poll_config["multisession_poll_interval_ms_at_capacity"]
                    if hb_ms > 0:
                        await _heartbeat_active_work_items()
                        try:
                            await asyncio.wait_for(loop_stop.wait(), timeout=hb_ms / 1000)
                        except asyncio.TimeoutError:
                            pass
                    elif at_cap_ms > 0:
                        try:
                            await asyncio.wait_for(loop_stop.wait(), timeout=at_cap_ms / 1000)
                        except asyncio.TimeoutError:
                            pass

            except asyncio.CancelledError:
                break
            except Exception as err:
                if loop_stop.is_set():
                    break

                if isinstance(err, BridgeFatalError):
                    fatal_exit = True
                    if is_expired_error_type(err.error_type):
                        bridge_logger.log_status(str(err))
                    elif is_suppressible_403(err):
                        _log_for_debugging(
                            f"[bridge:work] Suppressed 403 error: {err}"
                        )
                    else:
                        bridge_logger.log_error(str(err))
                        logger.error(err)
                    _log_event(
                        "tengu_bridge_fatal_error",
                        {"status": err.status, "error_type": err.error_type},
                    )
                    _log_for_diagnostics(
                        "info" if is_expired_error_type(err.error_type) else "error",
                        "bridge_fatal_error",
                        {"status": err.status, "error_type": err.error_type},
                    )
                    break

                err_msg = str(err)
                now = loop.time() * 1000

                if is_connection_error(err) or is_server_error(err):
                    if (
                        last_poll_error_time is not None
                        and now - last_poll_error_time
                        > _poll_sleep_detection_threshold_ms(backoff_config)
                    ):
                        _log_for_debugging(
                            f"[bridge:work] Detected system sleep "
                            f"({round((now - last_poll_error_time) / 1000)}s gap), "
                            f"resetting error budget"
                        )
                        _log_for_diagnostics(
                            "info",
                            "bridge_poll_sleep_detected",
                            {"gapMs": now - last_poll_error_time},
                        )
                        conn_error_start = None
                        conn_backoff = 0.0
                        general_error_start = None
                        general_backoff = 0.0

                    last_poll_error_time = now
                    if conn_error_start is None:
                        conn_error_start = now

                    elapsed = now - conn_error_start
                    if elapsed >= backoff_config.conn_give_up_ms:
                        bridge_logger.log_error(
                            f"Server unreachable for {round(elapsed / 60_000)} minutes, giving up."
                        )
                        _log_event(
                            "tengu_bridge_poll_give_up",
                            {"error_type": "connection", "elapsed_ms": elapsed},
                        )
                        _log_for_diagnostics(
                            "error",
                            "bridge_poll_give_up",
                            {"error_type": "connection", "elapsed_ms": elapsed},
                        )
                        fatal_exit = True
                        break

                    general_error_start = None
                    general_backoff = 0.0
                    conn_backoff = (
                        min(conn_backoff * 2, backoff_config.conn_cap_ms)
                        if conn_backoff
                        else backoff_config.conn_initial_ms
                    )
                    delay = _add_jitter(conn_backoff)
                    bridge_logger.log_verbose(
                        f"Connection error, retrying in {_format_delay(delay)} "
                        f"({round(elapsed / 1000)}s elapsed): {err_msg}"
                    )
                    bridge_logger.update_reconnecting_status(
                        _format_delay(delay), _format_duration_ms(elapsed)
                    )
                    if (
                        _get_poll_interval_config()["non_exclusive_heartbeat_interval_ms"] > 0
                    ):
                        await _heartbeat_active_work_items()
                    try:
                        await asyncio.wait_for(loop_stop.wait(), timeout=delay / 1000)
                    except asyncio.TimeoutError:
                        pass
                else:
                    if (
                        last_poll_error_time is not None
                        and now - last_poll_error_time
                        > _poll_sleep_detection_threshold_ms(backoff_config)
                    ):
                        _log_for_debugging(
                            f"[bridge:work] Detected system sleep "
                            f"({round((now - last_poll_error_time) / 1000)}s gap), "
                            f"resetting error budget"
                        )
                        _log_for_diagnostics(
                            "info",
                            "bridge_poll_sleep_detected",
                            {"gapMs": now - last_poll_error_time},
                        )
                        conn_error_start = None
                        conn_backoff = 0.0
                        general_error_start = None
                        general_backoff = 0.0

                    last_poll_error_time = now
                    if general_error_start is None:
                        general_error_start = now

                    elapsed = now - general_error_start
                    if elapsed >= backoff_config.general_give_up_ms:
                        bridge_logger.log_error(
                            f"Persistent errors for {round(elapsed / 60_000)} minutes, giving up."
                        )
                        _log_event(
                            "tengu_bridge_poll_give_up",
                            {"error_type": "general", "elapsed_ms": elapsed},
                        )
                        _log_for_diagnostics(
                            "error",
                            "bridge_poll_give_up",
                            {"error_type": "general", "elapsed_ms": elapsed},
                        )
                        fatal_exit = True
                        break

                    conn_error_start = None
                    conn_backoff = 0.0
                    general_backoff = (
                        min(general_backoff * 2, backoff_config.general_cap_ms)
                        if general_backoff
                        else backoff_config.general_initial_ms
                    )
                    delay = _add_jitter(general_backoff)
                    bridge_logger.log_verbose(
                        f"Poll failed, retrying in {_format_delay(delay)} "
                        f"({round(elapsed / 1000)}s elapsed): {err_msg}"
                    )
                    bridge_logger.update_reconnecting_status(
                        _format_delay(delay), _format_duration_ms(elapsed)
                    )
                    if (
                        _get_poll_interval_config()["non_exclusive_heartbeat_interval_ms"] > 0
                    ):
                        await _heartbeat_active_work_items()
                    try:
                        await asyncio.wait_for(loop_stop.wait(), timeout=delay / 1000)
                    except asyncio.TimeoutError:
                        pass

    finally:
        stop_task.cancel()

    # ----- Cleanup -----
    _stop_status_updates()
    bridge_logger.clear_status()

    loop_duration_ms = (loop.time() - loop_start_time) * 1000
    _log_event(
        "tengu_bridge_shutdown",
        {"active_sessions": len(active_sessions), "loop_duration_ms": loop_duration_ms},
    )
    _log_for_diagnostics(
        "info",
        "bridge_shutdown",
        {"active_sessions": len(active_sessions), "loop_duration_ms": loop_duration_ms},
    )

    sessions_to_archive: set[str] = set(active_sessions.keys())
    if initial_session_id:
        sessions_to_archive.add(initial_session_id)
    compat_id_snapshot = dict(session_compat_ids)

    if active_sessions:
        bridge_logger.log_status(
            f"Shutting down {len(active_sessions)} active session(s)\u2026"
        )
        shutdown_work_ids = dict(session_work_ids)

        for sid, handle in list(active_sessions.items()):
            _log_for_debugging(f"[bridge:shutdown] Sending SIGTERM to sessionId={sid}")
            handle.kill()

        grace_s = backoff_config.shutdown_grace_ms / 1000
        done_futs = [
            asyncio.ensure_future(
                _await_handle_done_raw(h)
            )
            for h in active_sessions.values()
        ]
        done, pending = await asyncio.wait(done_futs, timeout=grace_s)
        for t in pending:
            t.cancel()

        for sid, handle in active_sessions.items():
            _log_for_debugging(f"[bridge:shutdown] Force-killing stuck sessionId={sid}")
            handle.force_kill()

        for timer in session_timers.values():
            timer.cancel()
        session_timers.clear()

        if session_worktrees:
            remaining_worktrees = list(session_worktrees.values())
            session_worktrees.clear()
            _log_for_debugging(
                f"[bridge:shutdown] Cleaning up {len(remaining_worktrees)} worktree(s)"
            )
            await asyncio.gather(
                *[
                    _try_remove_worktree(api, wt)
                    for wt in remaining_worktrees
                ],
                return_exceptions=True,
            )

        await asyncio.gather(
            *[
                _try_stop_work(api, environment_id, work_id, session_id, bridge_logger)
                for session_id, work_id in shutdown_work_ids.items()
            ],
            return_exceptions=True,
        )

    if pending_cleanups:
        await asyncio.gather(*pending_cleanups, return_exceptions=True)

    # Single-session resumable shutdown: skip archive+deregister
    if (
        config.spawn_mode == "single-session"
        and initial_session_id
        and not fatal_exit
    ):
        bridge_logger.log_status(
            "Resume this session by running `claude remote-control --continue`"
        )
        _log_for_debugging(
            f"[bridge:shutdown] Skipping archive+deregister to allow resume of session {initial_session_id}"
        )
        return

    if sessions_to_archive:
        _log_for_debugging(
            f"[bridge:shutdown] Archiving {len(sessions_to_archive)} session(s)"
        )
        await asyncio.gather(
            *[
                _try_archive_session(
                    api,
                    compat_id_snapshot.get(sid, _to_compat_session_id(sid)),
                    sid,
                    bridge_logger,
                )
                for sid in sessions_to_archive
            ],
            return_exceptions=True,
        )

    try:
        await api.deregister_environment(environment_id)
        _log_for_debugging("[bridge:shutdown] Environment deregistered, bridge offline")
        bridge_logger.log_verbose("Environment deregistered.")
    except Exception as err:
        bridge_logger.log_verbose(
            f"Failed to deregister environment: {_error_message(err)}"
        )

    bridge_logger.log_verbose("Environment offline.")


# ---------------------------------------------------------------------------
# Async helpers for shutdown
# ---------------------------------------------------------------------------


async def _await_handle_done(
    handle: SessionHandle,
    callback: Callable[[SessionDoneStatus], None],
) -> None:
    try:
        status = await handle.done
        callback(status)
    except Exception:
        pass


async def _await_handle_done_raw(handle: SessionHandle) -> None:
    try:
        await handle.done
    except Exception:
        pass


async def _try_remove_worktree(api: BridgeApiClient, wt: dict) -> None:
    try:
        await api.remove_agent_worktree(
            wt["worktree_path"],
            wt.get("worktree_branch"),
            wt.get("git_root"),
            wt.get("hook_based"),
        )
    except Exception:
        pass


async def _try_stop_work(
    api: BridgeApiClient,
    environment_id: str,
    work_id: str,
    session_id: str,
    bridge_logger: BridgeLogger,
) -> None:
    try:
        await api.stop_work(environment_id, work_id, True)
    except Exception as err:
        bridge_logger.log_verbose(
            f"Failed to stop work {work_id} for session {session_id}: {_error_message(err)}"
        )


async def _try_archive_session(
    api: BridgeApiClient,
    compat_id: str,
    session_id: str,
    bridge_logger: BridgeLogger,
) -> None:
    try:
        await api.archive_session(compat_id)
    except Exception as err:
        bridge_logger.log_verbose(
            f"Failed to archive session {session_id}: {_error_message(err)}"
        )


# ---------------------------------------------------------------------------
# Poll interval config stub
# ---------------------------------------------------------------------------


def _get_poll_interval_config() -> dict[str, int]:
    """Return poll interval configuration. Mirrors getPollIntervalConfig() from pollConfig.ts."""
    return {
        "reclaim_older_than_ms": 30_000,
        "multisession_poll_interval_ms_at_capacity": 0,
        "multisession_poll_interval_ms_partial_capacity": 1_000,
        "multisession_poll_interval_ms_not_at_capacity": 2_000,
        "non_exclusive_heartbeat_interval_ms": 0,
    }


# ---------------------------------------------------------------------------
# URL / secret helpers (stubs for Node-specific modules)
# ---------------------------------------------------------------------------


def _build_sdk_url(session_ingress_url: str, session_id: str) -> str:
    base = session_ingress_url.rstrip("/")
    return f"{base}/v1/session_ingress/{session_id}"


def _build_ccr_v2_sdk_url(api_base_url: str, session_id: str) -> str:
    base = api_base_url.rstrip("/")
    return f"{base}/v1/code/sessions/{session_id}"


def _decode_work_secret(raw: str) -> dict[str, Any]:
    """Decode base64url-encoded JSON WorkSecret."""
    import base64
    import json

    # Add padding
    padded = raw + "=" * (4 - len(raw) % 4)
    decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
    return json.loads(decoded)


def _validate_bridge_id(value: str) -> bool:
    """Return True if the bridge session/environment ID is safe."""
    # Must not contain path separators or control characters
    return bool(value) and not re.search(r'[/\\<>:"|?*\x00-\x1f]', value)


def _safe_filename_id(session_id: str) -> str:
    """Return a safe filename fragment from a session ID."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)


def _get_remote_session_url(session_id: str, session_ingress_url: str) -> str:
    return f"https://claude.ai/code/sessions/{session_id}"


# ---------------------------------------------------------------------------
# ParsedArgs and parseArgs
# ---------------------------------------------------------------------------


@dataclass
class ParsedArgs:
    """Parsed CLI arguments for the bridge / remote-control subcommand."""

    verbose: bool = False
    sandbox: bool = False
    debug_file: str | None = None
    session_timeout_ms: int | None = None
    permission_mode: str | None = None
    name: str | None = None
    spawn_mode: "SpawnMode | None" = None
    capacity: int | None = None
    create_session_in_dir: bool | None = None
    session_id: str | None = None
    continue_session: bool = False
    help: bool = False
    error: str | None = None


def _parse_spawn_value(raw: str | None) -> "SpawnMode | str":
    if raw == "session":
        return "single-session"
    if raw == "same-dir":
        return "same-dir"
    if raw == "worktree":
        return "worktree"
    return f"--spawn requires one of: session, same-dir, worktree (got: {raw or '<missing>'})"


def _parse_capacity_value(raw: str | None) -> "int | str":
    try:
        n = int(raw or "")
        if n < 1:
            raise ValueError
        return n
    except (ValueError, TypeError):
        return f"--capacity requires a positive integer (got: {raw or '<missing>'})"


def parse_args(args: list[str]) -> ParsedArgs:
    """
    Parse CLI args for `claude remote-control`.

    Returns a ParsedArgs with .error set on any invalid combination.
    """
    parsed = ParsedArgs()
    i = 0

    def _make_error(msg: str) -> ParsedArgs:
        p = ParsedArgs(
            verbose=parsed.verbose,
            sandbox=parsed.sandbox,
            debug_file=parsed.debug_file,
            session_timeout_ms=parsed.session_timeout_ms,
            permission_mode=parsed.permission_mode,
            name=parsed.name,
            spawn_mode=parsed.spawn_mode,
            capacity=parsed.capacity,
            create_session_in_dir=parsed.create_session_in_dir,
            session_id=parsed.session_id,
            continue_session=parsed.continue_session,
            help=parsed.help,
            error=msg,
        )
        return p

    while i < len(args):
        arg = args[i]

        if arg in ("--help", "-h"):
            parsed.help = True
        elif arg in ("--verbose", "-v"):
            parsed.verbose = True
        elif arg == "--sandbox":
            parsed.sandbox = True
        elif arg == "--no-sandbox":
            parsed.sandbox = False
        elif arg == "--debug-file" and i + 1 < len(args):
            i += 1
            parsed.debug_file = os.path.realpath(args[i])
        elif arg.startswith("--debug-file="):
            parsed.debug_file = os.path.realpath(arg[len("--debug-file="):])
        elif arg == "--session-timeout" and i + 1 < len(args):
            i += 1
            parsed.session_timeout_ms = int(args[i]) * 1000
        elif arg.startswith("--session-timeout="):
            parsed.session_timeout_ms = int(arg[len("--session-timeout="):]) * 1000
        elif arg == "--permission-mode" and i + 1 < len(args):
            i += 1
            parsed.permission_mode = args[i]
        elif arg.startswith("--permission-mode="):
            parsed.permission_mode = arg[len("--permission-mode="):]
        elif arg == "--name" and i + 1 < len(args):
            i += 1
            parsed.name = args[i]
        elif arg.startswith("--name="):
            parsed.name = arg[len("--name="):]
        elif arg == "--session-id" and i + 1 < len(args):
            i += 1
            parsed.session_id = args[i]
            if not parsed.session_id:
                return _make_error("--session-id requires a value")
        elif arg.startswith("--session-id="):
            parsed.session_id = arg[len("--session-id="):]
            if not parsed.session_id:
                return _make_error("--session-id requires a value")
        elif arg in ("--continue", "-c"):
            parsed.continue_session = True
        elif arg == "--spawn" or arg.startswith("--spawn="):
            if parsed.spawn_mode is not None:
                return _make_error("--spawn may only be specified once")
            raw = arg[len("--spawn="):] if arg.startswith("--spawn=") else (
                args[i + 1] if i + 1 < len(args) else None
            )
            if not arg.startswith("--spawn="):
                i += 1
            v = _parse_spawn_value(raw)
            if v in ("single-session", "same-dir", "worktree"):
                parsed.spawn_mode = v  # type: ignore[assignment]
            else:
                return _make_error(v)  # type: ignore[arg-type]
        elif arg == "--capacity" or arg.startswith("--capacity="):
            if parsed.capacity is not None:
                return _make_error("--capacity may only be specified once")
            raw = arg[len("--capacity="):] if arg.startswith("--capacity=") else (
                args[i + 1] if i + 1 < len(args) else None
            )
            if not arg.startswith("--capacity="):
                i += 1
            v = _parse_capacity_value(raw)
            if isinstance(v, int):
                parsed.capacity = v
            else:
                return _make_error(v)
        elif arg == "--create-session-in-dir":
            parsed.create_session_in_dir = True
        elif arg == "--no-create-session-in-dir":
            parsed.create_session_in_dir = False
        else:
            return _make_error(
                f"Unknown argument: {arg}\nRun 'claude remote-control --help' for usage."
            )
        i += 1

    # Cross-validation
    if parsed.spawn_mode == "single-session" and parsed.capacity is not None:
        return _make_error(
            "--capacity cannot be used with --spawn=session (single-session mode has fixed capacity 1)."
        )

    if (parsed.session_id or parsed.continue_session) and (
        parsed.spawn_mode is not None
        or parsed.capacity is not None
        or parsed.create_session_in_dir is not None
    ):
        return _make_error(
            "--session-id and --continue cannot be used with --spawn, --capacity, or --create-session-in-dir."
        )

    if parsed.session_id and parsed.continue_session:
        return _make_error("--session-id and --continue cannot be used together.")

    return parsed


# ---------------------------------------------------------------------------
# bridgeMain — interactive CLI entrypoint
# ---------------------------------------------------------------------------


async def bridge_main(args: list[str]) -> None:
    """
    Main entry point for `claude remote-control`.

    Parses args, validates config, registers the bridge environment, and
    runs the poll loop until shutdown.
    """
    parsed = parse_args(args)

    if parsed.help:
        await _print_help()
        return

    if parsed.error:
        print(f"Error: {parsed.error}", file=sys.stderr)
        sys.exit(1)

    (
        verbose,
        sandbox,
        debug_file,
        session_timeout_ms,
        permission_mode,
        name,
        parsed_spawn_mode,
        parsed_capacity,
        parsed_create_session_in_dir,
        parsed_session_id,
        continue_session,
    ) = (
        parsed.verbose,
        parsed.sandbox,
        parsed.debug_file,
        parsed.session_timeout_ms,
        parsed.permission_mode,
        parsed.name,
        parsed.spawn_mode,
        parsed.capacity,
        parsed.create_session_in_dir,
        parsed.session_id,
        parsed.continue_session,
    )

    resume_session_id = parsed_session_id

    used_multi_session_feature = (
        parsed_spawn_mode is not None
        or parsed_capacity is not None
        or parsed_create_session_in_dir is not None
    )

    # In Python port: no GrowthBook gate; treat multi-session as always enabled
    multi_session_enabled = True

    if used_multi_session_feature and not multi_session_enabled:
        print(
            "Error: Multi-session Remote Control is not enabled for your account yet.",
            file=sys.stderr,
        )
        sys.exit(1)

    directory = os.path.realpath(".")

    # Auth check stub
    bridge_token = os.environ.get("CLAUDE_BRIDGE_ACCESS_TOKEN")
    if not bridge_token:
        print(BRIDGE_LOGIN_ERROR, file=sys.stderr)
        sys.exit(1)

    # Base URL
    base_url = os.environ.get(
        "CLAUDE_BRIDGE_BASE_URL", "https://api.anthropic.com"
    )
    if (
        base_url.startswith("http://")
        and "localhost" not in base_url
        and "127.0.0.1" not in base_url
    ):
        print(
            "Error: Remote Control base URL uses HTTP. Only HTTPS or localhost HTTP is allowed.",
            file=sys.stderr,
        )
        sys.exit(1)

    session_ingress_url = (
        os.environ.get("CLAUDE_BRIDGE_SESSION_INGRESS_URL", base_url)
        if os.environ.get("USER_TYPE") == "ant"
        and os.environ.get("CLAUDE_BRIDGE_SESSION_INGRESS_URL")
        else base_url
    )

    # Spawn mode determination
    saved_spawn_mode: SpawnMode | None = None
    worktree_available = _check_worktree_available(directory)

    if resume_session_id:
        spawn_mode: SpawnMode = "single-session"
    elif parsed_spawn_mode is not None:
        spawn_mode = parsed_spawn_mode
    elif saved_spawn_mode is not None:
        spawn_mode = saved_spawn_mode
    else:
        spawn_mode = "same-dir" if multi_session_enabled else "single-session"

    max_sessions = (
        1 if spawn_mode == "single-session" else (parsed_capacity or SPAWN_SESSIONS_DEFAULT)
    )
    pre_create_session = parsed_create_session_in_dir if parsed_create_session_in_dir is not None else True

    if spawn_mode == "worktree" and not worktree_available:
        print(
            "Error: Worktree mode requires a git repository or WorktreeCreate hooks configured. "
            "Use --spawn=session for single-session mode.",
            file=sys.stderr,
        )
        sys.exit(1)

    import uuid
    import socket

    branch = _get_git_branch(directory)
    git_repo_url = _get_git_remote_url(directory)
    machine_name = socket.gethostname()
    bridge_id = str(uuid.uuid4())

    from .api import create_bridge_api_client

    api_config = BridgeConfig(
        base_url=base_url,
        access_token=bridge_token,
    )
    api = create_bridge_api_client(api_config)

    config = BridgeConfig(
        base_url=base_url,
        access_token=bridge_token,
    )
    # Attach extended attributes for the bridge loop
    config.dir = directory  # type: ignore[attr-defined]
    config.machine_name = machine_name  # type: ignore[attr-defined]
    config.branch = branch  # type: ignore[attr-defined]
    config.git_repo_url = git_repo_url  # type: ignore[attr-defined]
    config.max_sessions = max_sessions  # type: ignore[attr-defined]
    config.spawn_mode = spawn_mode  # type: ignore[attr-defined]
    config.verbose = verbose  # type: ignore[attr-defined]
    config.sandbox = sandbox  # type: ignore[attr-defined]
    config.bridge_id = bridge_id  # type: ignore[attr-defined]
    config.worker_type = "claude_code"  # type: ignore[attr-defined]
    config.environment_id = str(uuid.uuid4())  # type: ignore[attr-defined]
    config.api_base_url = base_url  # type: ignore[attr-defined]
    config.session_ingress_url = session_ingress_url  # type: ignore[attr-defined]
    config.debug_file = debug_file  # type: ignore[attr-defined]
    config.session_timeout_ms = session_timeout_ms  # type: ignore[attr-defined]

    try:
        reg = await api.register_bridge_environment(config)
        environment_id = reg["environment_id"]
        environment_secret = reg["environment_secret"]
    except Exception as err:
        print(f"Error: {_error_message(err)}", file=sys.stderr)
        sys.exit(1)

    spawner = _create_session_spawner_stub(verbose, sandbox, debug_file, permission_mode)
    bridge_logger = _create_bridge_logger_stub(verbose)

    abort_event = asyncio.Event()

    loop = asyncio.get_event_loop()

    def _handle_sigint() -> None:
        _log_for_debugging("[bridge:shutdown] SIGINT received, shutting down")
        abort_event.set()

    def _handle_sigterm() -> None:
        _log_for_debugging("[bridge:shutdown] SIGTERM received, shutting down")
        abort_event.set()

    loop.add_signal_handler(signal_module.SIGINT, _handle_sigint)
    loop.add_signal_handler(signal_module.SIGTERM, _handle_sigterm)

    initial_session_id: str | None = None
    if pre_create_session:
        try:
            initial_session_id = await api.create_bridge_session(
                environment_id=environment_id,
                title=name,
                git_repo_url=git_repo_url,
                branch=branch,
            )
        except Exception as err:
            _log_for_debugging(
                f"[bridge:init] Session creation failed (non-fatal): {_error_message(err)}"
            )

    try:
        await run_bridge_loop(
            config=config,
            environment_id=environment_id,
            environment_secret=environment_secret,
            api=api,
            spawner=spawner,
            bridge_logger=bridge_logger,
            abort_event=abort_event,
            backoff_config=None,
            initial_session_id=initial_session_id,
            get_access_token=None,
        )
    finally:
        loop.remove_signal_handler(signal_module.SIGINT)
        loop.remove_signal_handler(signal_module.SIGTERM)

    sys.exit(0)


# ---------------------------------------------------------------------------
# BridgeHeadlessPermanentError + HeadlessBridgeOpts + runBridgeHeadless
# ---------------------------------------------------------------------------


class BridgeHeadlessPermanentError(Exception):
    """
    Thrown by run_bridge_headless for configuration issues the supervisor
    should NOT retry (trust not accepted, worktree unavailable, http-not-https).
    The daemon worker catches this and exits with EXIT_CODE_PERMANENT so the
    supervisor parks the worker instead of respawning it on backoff.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.name = "BridgeHeadlessPermanentError"


@dataclass
class HeadlessBridgeOpts:
    """Options for the non-interactive (daemon) bridge entrypoint."""

    dir: str
    spawn_mode: Literal["same-dir", "worktree"]
    capacity: int
    sandbox: bool
    create_session_on_start: bool
    get_access_token: Callable[[], str | None]
    on_auth_401: Callable[[str], Coroutine[Any, Any, bool]]
    log: Callable[[str], None]
    name: str | None = None
    permission_mode: str | None = None
    session_timeout_ms: int | None = None


async def run_bridge_headless(
    opts: HeadlessBridgeOpts,
    signal: asyncio.Event,
) -> None:
    """
    Non-interactive bridge entrypoint for the `remoteControl` daemon worker.

    Linear subset of bridge_main(): no readline dialogs, no stdin key handlers,
    no TUI, no sys.exit(). Config comes from the caller (daemon.json), auth
    comes via IPC (supervisor's AuthManager), logs go to the worker's stdout
    pipe. Throws on fatal errors — the worker catches and maps permanent vs
    transient to the right exit code.

    Resolves cleanly when `signal` is set and the poll loop tears down.
    """
    from .api import create_bridge_api_client

    directory = opts.dir
    log = opts.log

    os.chdir(directory)

    if not opts.get_access_token():
        raise Exception(BRIDGE_LOGIN_ERROR)

    base_url = os.environ.get("CLAUDE_BRIDGE_BASE_URL", "https://api.anthropic.com")
    if (
        base_url.startswith("http://")
        and "localhost" not in base_url
        and "127.0.0.1" not in base_url
    ):
        raise BridgeHeadlessPermanentError(
            "Remote Control base URL uses HTTP. Only HTTPS or localhost HTTP is allowed."
        )

    session_ingress_url = (
        os.environ.get("CLAUDE_BRIDGE_SESSION_INGRESS_URL", base_url)
        if os.environ.get("USER_TYPE") == "ant"
        and os.environ.get("CLAUDE_BRIDGE_SESSION_INGRESS_URL")
        else base_url
    )

    if opts.spawn_mode == "worktree" and not _check_worktree_available(directory):
        raise BridgeHeadlessPermanentError(
            f"Worktree mode requires a git repository or WorktreeCreate hooks. "
            f"Directory {directory} has neither."
        )

    branch = _get_git_branch(directory)
    git_repo_url = _get_git_remote_url(directory)

    import uuid
    import socket

    machine_name = socket.gethostname()
    bridge_id = str(uuid.uuid4())

    api_cfg = BridgeConfig(
        base_url=base_url,
        access_token=opts.get_access_token(),
    )
    api = create_bridge_api_client(api_cfg)

    config = BridgeConfig(base_url=base_url, access_token=opts.get_access_token())
    config.dir = directory  # type: ignore[attr-defined]
    config.machine_name = machine_name  # type: ignore[attr-defined]
    config.branch = branch  # type: ignore[attr-defined]
    config.git_repo_url = git_repo_url  # type: ignore[attr-defined]
    config.max_sessions = opts.capacity  # type: ignore[attr-defined]
    config.spawn_mode = opts.spawn_mode  # type: ignore[attr-defined]
    config.verbose = False  # type: ignore[attr-defined]
    config.sandbox = opts.sandbox  # type: ignore[attr-defined]
    config.bridge_id = bridge_id  # type: ignore[attr-defined]
    config.worker_type = "claude_code"  # type: ignore[attr-defined]
    config.environment_id = str(uuid.uuid4())  # type: ignore[attr-defined]
    config.api_base_url = base_url  # type: ignore[attr-defined]
    config.session_ingress_url = session_ingress_url  # type: ignore[attr-defined]
    config.session_timeout_ms = opts.session_timeout_ms  # type: ignore[attr-defined]

    try:
        reg = await api.register_bridge_environment(config)
        environment_id = reg["environment_id"]
        environment_secret = reg["environment_secret"]
    except Exception as err:
        raise Exception(f"Bridge registration failed: {_error_message(err)}") from err

    spawner = _create_session_spawner_stub(False, opts.sandbox, None, opts.permission_mode)
    bridge_logger = _create_headless_bridge_logger(log)
    bridge_logger.print_banner(config, environment_id)

    initial_session_id: str | None = None
    if opts.create_session_on_start:
        try:
            sid = await api.create_bridge_session(
                environment_id=environment_id,
                title=opts.name,
                git_repo_url=git_repo_url,
                branch=branch,
            )
            if sid:
                initial_session_id = sid
                log(f"created initial session {sid}")
        except Exception as err:
            log(f"session pre-creation failed (non-fatal): {_error_message(err)}")

    await run_bridge_loop(
        config=config,
        environment_id=environment_id,
        environment_secret=environment_secret,
        api=api,
        spawner=spawner,
        bridge_logger=bridge_logger,
        abort_event=signal,
        backoff_config=None,
        initial_session_id=initial_session_id,
        get_access_token=None,
    )


# ---------------------------------------------------------------------------
# Headless logger
# ---------------------------------------------------------------------------


def _create_headless_bridge_logger(log: Callable[[str], None]) -> BridgeLogger:
    """BridgeLogger adapter that routes everything to a single line-log fn."""

    class _HeadlessLogger(BridgeLogger):
        def print_banner(self, cfg: Any, env_id: str) -> None:
            log(
                f"registered environmentId={env_id} dir={cfg.dir} "
                f"spawnMode={cfg.spawn_mode} capacity={cfg.max_sessions}"
            )

        def log_session_start(self, sid: str, _prompt: str) -> None:
            log(f"session start {sid}")

        def log_session_complete(self, sid: str, ms: int) -> None:
            log(f"session complete {sid} ({ms}ms)")

        def log_session_failed(self, sid: str, err: str) -> None:
            log(f"session failed {sid}: {err}")

        def log_status(self, s: str) -> None:
            log(s)

        def log_verbose(self, s: str) -> None:
            log(s)

        def log_error(self, s: str) -> None:
            log(f"error: {s}")

        def log_reconnected(self, ms: int) -> None:
            log(f"reconnected after {ms}ms")

        def add_session(self, sid: str, _url: str) -> None:
            log(f"session attached {sid}")

        def remove_session(self, sid: str) -> None:
            log(f"session detached {sid}")

        def update_idle_status(self) -> None:
            pass

        def update_reconnecting_status(self, delay: str, elapsed: str) -> None:
            pass

        def update_session_status(self, *_: Any) -> None:
            pass

        def update_session_activity(self, *_: Any) -> None:
            pass

        def update_session_count(self, *_: Any) -> None:
            pass

        def update_failed_status(self, *_: Any) -> None:
            pass

        def set_spawn_mode_display(self, *_: Any) -> None:
            pass

        def set_repo_info(self, *_: Any) -> None:
            pass

        def set_debug_log_path(self, *_: Any) -> None:
            pass

        def set_attached(self, *_: Any) -> None:
            pass

        def set_session_title(self, *_: Any) -> None:
            pass

        def clear_status(self) -> None:
            pass

        def toggle_qr(self) -> None:
            pass

        def refresh_display(self) -> None:
            pass

    return _HeadlessLogger()


# ---------------------------------------------------------------------------
# Interactive logger stub (for bridgeMain)
# ---------------------------------------------------------------------------


def _create_bridge_logger_stub(verbose: bool) -> BridgeLogger:
    """Simple stdout logger for the interactive CLI path."""

    class _StdoutLogger(BridgeLogger):
        def print_banner(self, cfg: Any, env_id: str) -> None:
            print(f"Remote Control started. Environment: {env_id}")

        def log_session_start(self, sid: str, _prompt: str) -> None:
            print(f"Session started: {sid}")

        def log_session_complete(self, sid: str, ms: int) -> None:
            print(f"Session complete: {sid} ({ms}ms)")

        def log_session_failed(self, sid: str, err: str) -> None:
            print(f"Session failed: {sid}: {err}", file=sys.stderr)

        def log_status(self, s: str) -> None:
            print(s)

        def log_verbose(self, s: str) -> None:
            if verbose:
                print(s)

        def log_error(self, s: str) -> None:
            print(f"Error: {s}", file=sys.stderr)

        def log_reconnected(self, ms: int) -> None:
            print(f"Reconnected after {ms}ms")

        def add_session(self, sid: str, url: str) -> None:
            print(f"Session attached: {sid} ({url})")

        def remove_session(self, sid: str) -> None:
            print(f"Session detached: {sid}")

        def update_idle_status(self) -> None:
            pass

        def update_reconnecting_status(self, delay: str, elapsed: str) -> None:
            pass

        def update_session_status(self, *_: Any) -> None:
            pass

        def update_session_activity(self, *_: Any) -> None:
            pass

        def update_session_count(self, *_: Any) -> None:
            pass

        def update_failed_status(self, *_: Any) -> None:
            pass

        def set_spawn_mode_display(self, *_: Any) -> None:
            pass

        def set_repo_info(self, *_: Any) -> None:
            pass

        def set_debug_log_path(self, *_: Any) -> None:
            pass

        def set_attached(self, *_: Any) -> None:
            pass

        def set_session_title(self, *_: Any) -> None:
            pass

        def clear_status(self) -> None:
            pass

        def toggle_qr(self) -> None:
            pass

        def refresh_display(self) -> None:
            pass

    return _StdoutLogger()


# ---------------------------------------------------------------------------
# Spawner stub
# ---------------------------------------------------------------------------


def _create_session_spawner_stub(
    verbose: bool,
    sandbox: bool,
    debug_file: str | None,
    permission_mode: str | None,
) -> SessionSpawner:
    """Stub SessionSpawner for use in bridgeMain (no actual process spawning in port)."""

    class _StubSpawner(SessionSpawner):
        def spawn(self, opts: SessionSpawnOpts, directory: str) -> SessionHandle:
            raise NotImplementedError(
                "Session spawning requires the full Claude Code runtime."
            )

    return _StubSpawner()


# ---------------------------------------------------------------------------
# Git helpers (stubs)
# ---------------------------------------------------------------------------


def _check_worktree_available(directory: str) -> bool:
    """Return True if git is available in the given directory."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=directory,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_git_branch(directory: str) -> str | None:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _get_git_remote_url(directory: str) -> str | None:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------


async def _print_help() -> None:
    help_text = """
Remote Control - Connect your local environment to claude.ai/code

USAGE
  claude remote-control [options]

OPTIONS
  --name <name>                    Name for the session (shown in claude.ai/code)
  -c, --continue                   Resume the last session in this directory
  --session-id <id>                Resume a specific session by ID (cannot be
                                   used with spawn flags or --continue)
  --permission-mode <mode>         Permission mode for spawned sessions
  --debug-file <path>              Write debug logs to file
  -v, --verbose                    Enable verbose output
  -h, --help                       Show this help
  --spawn <mode>                   Spawn mode: same-dir, worktree, session
                                   (default: same-dir)
  --capacity <N>                   Max concurrent sessions in worktree or
                                   same-dir mode (default: 32)
  --[no-]create-session-in-dir     Pre-create a session in the current
                                   directory (default: on)

DESCRIPTION
  Remote Control allows you to control sessions on your local device from
  claude.ai/code. Run this command in the directory you want to work in,
  then connect from the Claude app or web.

NOTES
  - You must be logged in with a Claude account that has a subscription
  - Run `claude` first in the directory to accept the workspace trust dialog
"""
    print(help_text)
