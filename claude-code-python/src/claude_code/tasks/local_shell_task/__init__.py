"""LocalShellTask — interactive bash task that runs in the REPL.

Ported from tasks/LocalShellTask/
"""
from __future__ import annotations

from .guards import BashTaskKind, is_local_shell_task
from .kill_shell_tasks import kill_shell_tasks_for_agent


class LocalShellTask:
    """Represents a running local shell (bash) task."""

    type = "local_bash"
    name = "LocalShellTask"

    @classmethod
    async def kill(cls, task_id: str, set_app_state) -> None:
        """Kill a specific shell task by ID."""
        def _update(prev: dict) -> dict:
            tasks = dict(prev.get("tasks", {}))
            if task_id in tasks:
                tasks[task_id] = {**tasks[task_id], "status": "killed"}
            return {**prev, "tasks": tasks}
        set_app_state(_update)


__all__ = [
    "LocalShellTask",
    "BashTaskKind",
    "is_local_shell_task",
    "kill_shell_tasks_for_agent",
]
