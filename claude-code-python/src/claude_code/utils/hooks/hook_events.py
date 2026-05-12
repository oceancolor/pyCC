"""
Hook event system for broadcasting hook execution events.

This module provides a generic event system that is separate from the
main message stream. Handlers can register to receive events and decide
what to do with them (e.g., convert to SDK messages, log, etc.).
"""

from __future__ import annotations

import asyncio
from typing import Callable, Dict, List, Literal, Optional, Union

from ..log import log_for_debugging

# Hook events that are always emitted regardless of the includeHookEvents
# option. These are low-noise lifecycle events that are backwards-compatible.
ALWAYS_EMITTED_HOOK_EVENTS = frozenset(["SessionStart", "Setup"])

# All recognized hook events
HOOK_EVENTS = [
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionDenied",
    "Notification", "UserPromptSubmit", "SessionStart", "Stop", "StopFailure",
    "SubagentStart", "SubagentStop", "PreCompact", "PostCompact",
    "PermissionRequest", "Setup", "TeammateIdle", "TaskCreated", "TaskCompleted",
    "Elicitation", "ElicitationResult", "ConfigChange", "InstructionsLoaded",
    "WorktreeCreate", "WorktreeRemove", "CwdChanged", "FileChanged", "SessionEnd",
]

MAX_PENDING_EVENTS = 100


class HookStartedEvent:
    def __init__(self, hook_id: str, hook_name: str, hook_event: str) -> None:
        self.type: Literal["started"] = "started"
        self.hook_id = hook_id
        self.hook_name = hook_name
        self.hook_event = hook_event


class HookProgressEvent:
    def __init__(
        self,
        hook_id: str,
        hook_name: str,
        hook_event: str,
        stdout: str,
        stderr: str,
        output: str,
    ) -> None:
        self.type: Literal["progress"] = "progress"
        self.hook_id = hook_id
        self.hook_name = hook_name
        self.hook_event = hook_event
        self.stdout = stdout
        self.stderr = stderr
        self.output = output


class HookResponseEvent:
    def __init__(
        self,
        hook_id: str,
        hook_name: str,
        hook_event: str,
        output: str,
        stdout: str,
        stderr: str,
        outcome: str,
        exit_code: Optional[int] = None,
    ) -> None:
        self.type: Literal["response"] = "response"
        self.hook_id = hook_id
        self.hook_name = hook_name
        self.hook_event = hook_event
        self.output = output
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.outcome = outcome  # 'success' | 'error' | 'cancelled'


HookExecutionEvent = Union[HookStartedEvent, HookProgressEvent, HookResponseEvent]
HookEventHandler = Callable[[HookExecutionEvent], None]

_pending_events: List[HookExecutionEvent] = []
_event_handler: Optional[HookEventHandler] = None
_all_hook_events_enabled: bool = False


def register_hook_event_handler(handler: Optional[HookEventHandler]) -> None:
    global _event_handler
    _event_handler = handler
    if handler and _pending_events:
        for event in list(_pending_events):
            handler(event)
        _pending_events.clear()


def _emit(event: HookExecutionEvent) -> None:
    if _event_handler:
        _event_handler(event)
    else:
        _pending_events.append(event)
        if len(_pending_events) > MAX_PENDING_EVENTS:
            _pending_events.pop(0)


def _should_emit(hook_event: str) -> bool:
    if hook_event in ALWAYS_EMITTED_HOOK_EVENTS:
        return True
    return _all_hook_events_enabled and hook_event in HOOK_EVENTS


def emit_hook_started(hook_id: str, hook_name: str, hook_event: str) -> None:
    if not _should_emit(hook_event):
        return
    _emit(HookStartedEvent(hook_id=hook_id, hook_name=hook_name, hook_event=hook_event))


def emit_hook_progress(
    *,
    hook_id: str,
    hook_name: str,
    hook_event: str,
    stdout: str,
    stderr: str,
    output: str,
) -> None:
    if not _should_emit(hook_event):
        return
    _emit(
        HookProgressEvent(
            hook_id=hook_id,
            hook_name=hook_name,
            hook_event=hook_event,
            stdout=stdout,
            stderr=stderr,
            output=output,
        )
    )


def start_hook_progress_interval(
    *,
    hook_id: str,
    hook_name: str,
    hook_event: str,
    get_output: Callable[[], "asyncio.Coroutine[None, None, Dict[str, str]]"],
    interval_ms: int = 1000,
) -> Callable[[], None]:
    """Start a periodic progress reporting interval. Returns a stop function."""
    if not _should_emit(hook_event):
        return lambda: None

    last_emitted_output: List[str] = [""]
    task: List[Optional[asyncio.Task]] = [None]
    stopped: List[bool] = [False]

    async def _poll() -> None:
        while not stopped[0]:
            try:
                await asyncio.sleep(interval_ms / 1000.0)
                result = await get_output()
                output = result.get("output", "")
                if output != last_emitted_output[0]:
                    last_emitted_output[0] = output
                    emit_hook_progress(
                        hook_id=hook_id,
                        hook_name=hook_name,
                        hook_event=hook_event,
                        stdout=result.get("stdout", ""),
                        stderr=result.get("stderr", ""),
                        output=output,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        pass

    if loop and loop.is_running():
        task[0] = loop.create_task(_poll())

    def stop() -> None:
        stopped[0] = True
        if task[0]:
            task[0].cancel()

    return stop


def emit_hook_response(
    *,
    hook_id: str,
    hook_name: str,
    hook_event: str,
    output: str,
    stdout: str,
    stderr: str,
    outcome: str,
    exit_code: Optional[int] = None,
) -> None:
    output_to_log = stdout or stderr or output
    if output_to_log:
        log_for_debugging(
            f"Hook {hook_name} ({hook_event}) {outcome}:\n{output_to_log}"
        )

    if not _should_emit(hook_event):
        return

    _emit(
        HookResponseEvent(
            hook_id=hook_id,
            hook_name=hook_name,
            hook_event=hook_event,
            output=output,
            stdout=stdout,
            stderr=stderr,
            outcome=outcome,
            exit_code=exit_code,
        )
    )


def set_all_hook_events_enabled(enabled: bool) -> None:
    """Enable emission of all hook event types."""
    global _all_hook_events_enabled
    _all_hook_events_enabled = enabled


def clear_hook_event_state() -> None:
    """Reset all hook event state (useful for testing)."""
    global _event_handler, _all_hook_events_enabled
    _event_handler = None
    _pending_events.clear()
    _all_hook_events_enabled = False
