"""Shared task stop logic. Ported from tasks/stopTask.ts"""
from __future__ import annotations
from typing import Any, Callable, Dict, Optional


class StopTaskError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


async def stop_task(
    task_id: str,
    get_app_state: Callable,
    set_app_state: Callable,
) -> dict:
    app_state = get_app_state()
    tasks = app_state.get("tasks", {})
    task = tasks.get(task_id)

    if not task:
        raise StopTaskError(f"No task found with ID: {task_id}", "not_found")

    if task.get("status") != "running":
        raise StopTaskError(
            f"Task {task_id} is not running (status: {task.get('status')})",
            "not_running",
        )

    from claude_code.tasks_module import get_task_by_type
    task_impl = get_task_by_type(task.get("type", ""))
    if not task_impl:
        raise StopTaskError(f"Unsupported task type: {task.get('type')}", "unsupported_type")

    await task_impl.kill(task_id, set_app_state)

    command = task.get("command") or task.get("description")
    return {"task_id": task_id, "task_type": task.get("type"), "command": command}
