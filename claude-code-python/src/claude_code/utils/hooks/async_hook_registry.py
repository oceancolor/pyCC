"""
Async hook registry - manages pending async hooks.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from .hook_events import emit_hook_response, start_hook_progress_interval


class PendingAsyncHook:
    def __init__(
        self,
        process_id: str,
        hook_id: str,
        hook_name: str,
        hook_event: str,
        command: str,
        timeout: int,
        stop_progress_interval: Callable[[], None],
        tool_name: Optional[str] = None,
        plugin_id: Optional[str] = None,
        shell_command: Optional[Any] = None,
    ) -> None:
        self.process_id = process_id
        self.hook_id = hook_id
        self.hook_name = hook_name
        self.hook_event = hook_event
        self.tool_name = tool_name
        self.plugin_id = plugin_id
        self.start_time = int(time.time() * 1000)
        self.timeout = timeout
        self.command = command
        self.response_attachment_sent = False
        self.shell_command = shell_command
        self.stop_progress_interval = stop_progress_interval


# Global registry state
_pending_hooks: Dict[str, PendingAsyncHook] = {}


def register_pending_async_hook(
    *,
    process_id: str,
    hook_id: str,
    async_response: Dict[str, Any],
    hook_name: str,
    hook_event: str,
    command: str,
    shell_command: Any,
    tool_name: Optional[str] = None,
    plugin_id: Optional[str] = None,
) -> None:
    """Register a pending async hook."""
    timeout = async_response.get("asyncTimeout", 15000)

    async def get_output() -> Dict[str, str]:
        hook = _pending_hooks.get(process_id)
        if not hook or not hook.shell_command:
            return {"stdout": "", "stderr": "", "output": ""}
        try:
            task_output = getattr(hook.shell_command, "task_output", None)
            if not task_output:
                return {"stdout": "", "stderr": "", "output": ""}
            stdout = await task_output.get_stdout() if hasattr(task_output, "get_stdout") else ""
            stderr = task_output.get_stderr() if hasattr(task_output, "get_stderr") else ""
            return {"stdout": stdout, "stderr": stderr, "output": stdout + stderr}
        except Exception:
            return {"stdout": "", "stderr": "", "output": ""}

    stop_progress = start_hook_progress_interval(
        hook_id=hook_id,
        hook_name=hook_name,
        hook_event=hook_event,
        get_output=get_output,
    )

    _pending_hooks[process_id] = PendingAsyncHook(
        process_id=process_id,
        hook_id=hook_id,
        hook_name=hook_name,
        hook_event=hook_event,
        command=command,
        timeout=timeout,
        stop_progress_interval=stop_progress,
        tool_name=tool_name,
        plugin_id=plugin_id,
        shell_command=shell_command,
    )


def get_pending_async_hook(process_id: str) -> Optional[PendingAsyncHook]:
    """Get a pending async hook by process ID."""
    return _pending_hooks.get(process_id)


def remove_pending_async_hook(process_id: str) -> None:
    """Remove and clean up a pending async hook."""
    hook = _pending_hooks.pop(process_id, None)
    if hook:
        hook.stop_progress_interval()


def get_all_pending_async_hooks() -> List[PendingAsyncHook]:
    """Get all pending async hooks."""
    return list(_pending_hooks.values())


def clear_pending_async_hooks() -> None:
    """Clear all pending async hooks (for testing)."""
    for hook in list(_pending_hooks.values()):
        hook.stop_progress_interval()
    _pending_hooks.clear()
