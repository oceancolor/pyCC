"""InProcessTeammateTask — runs a teammate agent in-process.

Ported from tasks/InProcessTeammateTask/
"""
from __future__ import annotations

from .types import InProcessTeammateTaskState, TeammateIdentity
from typing import Callable


class InProcessTeammateTask:
    """An in-process teammate task that runs a sub-agent asynchronously."""

    type = "in_process_teammate"
    name = "InProcessTeammateTask"

    @classmethod
    async def kill(cls, task_id: str, set_app_state: Callable) -> None:
        def _update(prev: dict) -> dict:
            tasks = dict(prev.get("tasks", {}))
            if task_id in tasks:
                tasks[task_id] = {**tasks[task_id], "status": "killed"}
            return {**prev, "tasks": tasks}
        set_app_state(_update)


__all__ = [
    "InProcessTeammateTask",
    "InProcessTeammateTaskState",
    "TeammateIdentity",
]
