"""LocalShellTask type guards. Ported from tasks/LocalShellTask/guards.ts"""
from __future__ import annotations
from typing import Any


def is_local_shell_task(task: Any) -> bool:
    return (
        isinstance(task, dict)
        and task.get("type") == "local_bash"
    )
