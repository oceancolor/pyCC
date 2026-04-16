"""
In-Process Teammate Helpers

Helper functions for in-process teammate integration.
Provides utilities to:
- Find task ID by agent name
- Handle plan approval responses
- Update awaitingPlanApproval state
- Detect permission-related messages
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Type aliases (stubs matching TS signatures)
# ---------------------------------------------------------------------------

AppState = Any  # dict-like state object
SetAppState = Callable[[Callable[[AppState], AppState]], None]


def _is_in_process_teammate_task(task: dict) -> bool:
    """Check whether a task dict is an in-process teammate task."""
    return task.get("type") == "in_process_teammate"


def _update_task_state(
    task_id: str,
    set_app_state: SetAppState,
    updater: Callable[[dict], dict],
) -> None:
    """Apply an updater to a specific task inside AppState."""

    def _apply(prev: AppState) -> AppState:
        tasks = dict(prev.get("tasks", {}))
        if task_id in tasks:
            tasks[task_id] = updater(tasks[task_id])
        return {**prev, "tasks": tasks}

    set_app_state(_apply)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def find_in_process_teammate_task_id(
    agent_name: str,
    app_state: AppState,
) -> Optional[str]:
    """Find the task ID for an in-process teammate by agent name.

    Args:
        agent_name: The agent name (e.g. "researcher").
        app_state: Current AppState dict.

    Returns:
        Task ID if found, None otherwise.
    """
    for task in app_state.get("tasks", {}).values():
        if (
            _is_in_process_teammate_task(task)
            and task.get("identity", {}).get("agentName") == agent_name
        ):
            return task.get("id")
    return None


def set_awaiting_plan_approval(
    task_id: str,
    set_app_state: SetAppState,
    awaiting: bool,
) -> None:
    """Set awaitingPlanApproval state for an in-process teammate.

    Args:
        task_id: Task ID of the in-process teammate.
        set_app_state: AppState setter callable.
        awaiting: Whether teammate is awaiting plan approval.
    """
    _update_task_state(
        task_id,
        set_app_state,
        lambda task: {**task, "awaitingPlanApproval": awaiting},
    )


def handle_plan_approval_response(
    task_id: str,
    _response: Any,
    set_app_state: SetAppState,
) -> None:
    """Handle plan approval response for an in-process teammate.

    Resets awaitingPlanApproval to False. The permissionMode from the
    response is handled separately by the agent loop.

    Args:
        task_id: Task ID of the in-process teammate.
        _response: The plan approval response message (reserved for future use).
        set_app_state: AppState setter callable.
    """
    set_awaiting_plan_approval(task_id, set_app_state, False)


# ---------------------------------------------------------------------------
# Permission delegation helpers
# ---------------------------------------------------------------------------


def _is_permission_response(message_text: str) -> bool:
    """Stub: detect tool permission response messages."""
    return "__permission_response__" in message_text


def _is_sandbox_permission_response(message_text: str) -> bool:
    """Stub: detect sandbox (network host) permission response messages."""
    return "__sandbox_permission__" in message_text


def is_permission_related_response(message_text: str) -> bool:
    """Check if a message is a permission-related response.

    Handles both tool permissions and sandbox (network host) permissions.

    Args:
        message_text: The raw message text to check.

    Returns:
        True if the message is a permission response.
    """
    return _is_permission_response(message_text) or _is_sandbox_permission_response(
        message_text
    )
