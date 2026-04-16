"""Kill shell tasks for agent. Ported from tasks/LocalShellTask/killShellTasks.ts (76L)"""
from __future__ import annotations
from typing import Any, Callable


def kill_shell_tasks_for_agent(agent_id: str, set_app_state: Callable) -> None:
    """Kill all local_bash tasks spawned by the given agent."""
    def _update(prev: dict) -> dict:
        tasks = dict(prev.get("tasks", {}))
        updated = {}
        for tid, task in tasks.items():
            if (task.get("type") == "local_bash"
                    and task.get("agent_id") == agent_id
                    and task.get("status") == "running"):
                updated[tid] = {**task, "status": "killed"}
            else:
                updated[tid] = task
        return {**prev, "tasks": {**tasks, **updated}}

    set_app_state(_update)
