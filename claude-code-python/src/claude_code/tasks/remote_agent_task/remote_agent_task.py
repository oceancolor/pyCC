"""RemoteAgentTask (stub). Ported from tasks/RemoteAgentTask/."""
from __future__ import annotations
from typing import Callable


class RemoteAgentTask:
    type = "remote_agent"
    name = "RemoteAgentTask"

    @classmethod
    async def kill(cls, task_id: str, set_app_state: Callable) -> None:
        def _update(prev: dict) -> dict:
            tasks = dict(prev.get("tasks", {}))
            if task_id in tasks:
                tasks[task_id] = {**tasks[task_id], "status": "killed"}
            return {**prev, "tasks": tasks}
        set_app_state(_update)
