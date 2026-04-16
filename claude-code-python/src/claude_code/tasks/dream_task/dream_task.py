"""DreamTask. Ported from tasks/DreamTask/DreamTask.ts (157L, stub)."""
from __future__ import annotations
from typing import Callable


class DreamTask:
    type = "dream"
    name = "DreamTask"

    @classmethod
    async def kill(cls, task_id: str, set_app_state: Callable) -> None:
        def _update(prev: dict) -> dict:
            tasks = dict(prev.get("tasks", {}))
            if task_id in tasks:
                tasks[task_id] = {**tasks[task_id], "status": "killed"}
            return {**prev, "tasks": tasks}
        set_app_state(_update)
