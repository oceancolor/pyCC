"""LocalAgentTask. Ported from tasks/LocalAgentTask/ (stub)."""
from __future__ import annotations
from typing import Any, Callable


class LocalAgentTask:
    type = "local_agent"
    name = "LocalAgentTask"

    @classmethod
    async def kill(cls, task_id: str, set_app_state: Callable) -> None:
        def _update(prev: dict) -> dict:
            tasks = dict(prev.get("tasks", {}))
            if task_id in tasks:
                tasks[task_id] = {**tasks[task_id], "status": "killed"}
            return {**prev, "tasks": tasks}
        set_app_state(_update)
