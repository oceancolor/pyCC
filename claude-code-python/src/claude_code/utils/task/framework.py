"""Task framework: AppState task management helpers. Ported from utils/task/framework.ts"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, TypeVar

# Standard polling interval for all tasks
POLL_INTERVAL_MS = 1000

# Duration to display killed tasks before eviction
STOPPED_DISPLAY_MS = 3_000

# Grace period for terminal local_agent tasks in the coordinator panel
PANEL_GRACE_MS = 30_000


TaskState = Dict[str, Any]  # Mirrors the TypeScript TaskState union
AppState = Dict[str, Any]   # Simplified mirror of TypeScript AppState
SetAppState = Callable[[Callable[[AppState], AppState]], None]

T = TypeVar("T")


class TaskAttachment:
    """Mirrors the TypeScript TaskAttachment type."""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        status: str,
        description: str,
        delta_summary: Optional[str] = None,
        tool_use_id: Optional[str] = None,
    ) -> None:
        self.type = "task_status"
        self.task_id = task_id
        self.tool_use_id = tool_use_id
        self.task_type = task_type
        self.status = status
        self.description = description
        self.delta_summary = delta_summary

    def to_dict(self) -> dict:
        d: dict = {
            "type": self.type,
            "taskId": self.task_id,
            "taskType": self.task_type,
            "status": self.status,
            "description": self.description,
            "deltaSummary": self.delta_summary,
        }
        if self.tool_use_id is not None:
            d["toolUseId"] = self.tool_use_id
        return d


def update_task_state(
    task_id: str,
    set_app_state: SetAppState,
    updater: Callable[[TaskState], TaskState],
) -> None:
    """Update a task's state in AppState.

    Skips the state update if the task is not found or the updater returns the
    same reference (no-op early return).

    Args:
        task_id: The ID of the task to update.
        set_app_state: A function that accepts a state-updater callback.
        updater: A function that takes the current task state and returns the
            new state. Return the same object to skip the update.
    """

    def _state_updater(prev: AppState) -> AppState:
        tasks: dict = prev.get("tasks") or {}
        task = tasks.get(task_id)
        if task is None:
            return prev
        updated = updater(task)
        if updated is task:
            return prev
        return {**prev, "tasks": {**tasks, task_id: updated}}

    set_app_state(_state_updater)


def register_task(task: TaskState, set_app_state: SetAppState) -> None:
    """Register a new task in AppState.

    If a task with the same ID already exists it is replaced.

    Args:
        task: The task state to register. Must have an ``"id"`` key.
        set_app_state: A function that accepts a state-updater callback.
    """
    task_id: str = task["id"]

    def _state_updater(prev: AppState) -> AppState:
        tasks: dict = dict(prev.get("tasks") or {})
        tasks[task_id] = task
        return {**prev, "tasks": tasks}

    set_app_state(_state_updater)


def evict_task(task_id: str, set_app_state: SetAppState) -> None:
    """Remove a task from AppState.

    Args:
        task_id: The ID of the task to evict.
        set_app_state: A function that accepts a state-updater callback.
    """

    def _state_updater(prev: AppState) -> AppState:
        tasks: dict = dict(prev.get("tasks") or {})
        tasks.pop(task_id, None)
        return {**prev, "tasks": tasks}

    set_app_state(_state_updater)
