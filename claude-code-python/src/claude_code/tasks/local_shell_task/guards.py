"""
LocalShellTask type guards.
Ported from tasks/LocalShellTask/guards.ts

Pure type definitions and type guards for LocalShellTask state.
Extracted so non-React consumers don't pull React/Ink into the module graph.
"""
from __future__ import annotations

from typing import Any, Literal, Optional


BashTaskKind = Literal["bash", "monitor"]


def is_local_shell_task(task: Any) -> bool:
    """Return True if *task* is a LocalShellTask state object."""
    return (
        isinstance(task, dict)
        and task.get("type") == "local_bash"
    )
