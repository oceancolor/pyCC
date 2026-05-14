"""
LocalShellTask type guards.
Ported from tasks/LocalShellTask/guards.ts

Pure type definitions and type guards for LocalShellTask state.
Extracted so non-React consumers don't pull React/Ink into the module graph.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


BashTaskKind = Literal["bash", "monitor"]


class LocalShellTaskState(TypedDict, total=False):
    """State shape for a running bash task (keep 'local_bash' for session-state compat)."""
    id: str
    type: Literal["local_bash"]
    command: str
    result: Optional[dict]          # {"code": int, "interrupted": bool}
    completion_status_sent_in_attachment: bool
    shell_command: Optional[Any]    # ShellCommand
    last_reported_total_lines: int
    is_backgrounded: bool
    agent_id: Optional[str]
    kind: Optional[BashTaskKind]


def is_local_shell_task(task: Any) -> bool:
    """Return True if *task* is a LocalShellTask state object."""
    return (
        isinstance(task, dict)
        and task.get("type") == "local_bash"
    )
