"""
LocalMainSessionTask - Handles backgrounding the main session query.

When user presses Ctrl+B twice during a query, the session is "backgrounded":
- The query continues running in the background
- The UI clears to a fresh prompt
- A notification is sent when the query completes

This reuses the LocalAgentTask state structure since the behavior is similar.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from ...constants.xml import (
    OUTPUT_FILE_TAG,
    STATUS_TAG,
    SUMMARY_TAG,
    TASK_ID_TAG,
    TASK_NOTIFICATION_TAG,
    TOOL_USE_ID_TAG,
)
from ...services.token_estimation import rough_token_count_estimation
from ...task import create_task_state_base
from ...utils.abort_controller import create_abort_controller
from ...utils.agent_context import run_with_agent_context, SubagentContext
from ...utils.cleanup_registry import register_cleanup
from ...utils.debug import log_for_debugging
from ...utils.log import log_error
from ...utils.message_queue_manager import enqueue_pending_notification
from ...utils.sdk_event_queue import emit_task_terminated_sdk
from ...utils.session_storage import (
    get_agent_transcript_path,
    record_sidechain_transcript,
)
from ...utils.task.disk_output import (
    evict_task_output,
    get_task_output_path,
    init_task_output_as_symlink,
)
from ...utils.task.framework import register_task, update_task_state
from ..local_agent_task.local_agent_task import LocalAgentTaskState

if TYPE_CHECKING:
    from ...query import QueryParams
    from ...task import SetAppState
    from ...tools.agent_tool.load_agents_dir import AgentDefinition, CustomAgentDefinition
    from ...types.message import Message


# Main session tasks use LocalAgentTaskState with agentType='main-session'
@dataclass
class LocalMainSessionTaskState(LocalAgentTaskState):
    agent_type: str = "main-session"


# Default agent definition for main session tasks when no agent is specified.
DEFAULT_MAIN_SESSION_AGENT: dict[str, Any] = {
    "agentType": "main-session",
    "whenToUse": "Main session query",
    "source": "userSettings",
    "getSystemPrompt": lambda: "",
}

# Alphabet for generating task IDs
_TASK_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"

# Max recent activities to keep for display
_MAX_RECENT_ACTIVITIES = 5


def _generate_main_session_task_id() -> str:
    """Generate a unique task ID for main session tasks.
    Uses 's' prefix to distinguish from agent tasks ('a' prefix).
    """
    raw = secrets.token_bytes(8)
    task_id = "s"
    for byte in raw:
        task_id += _TASK_ID_ALPHABET[byte % len(_TASK_ID_ALPHABET)]
    return task_id


def register_main_session_task(
    description: str,
    set_app_state: "SetAppState",
    main_thread_agent_definition: Optional["AgentDefinition"] = None,
    existing_abort_controller: Optional[Any] = None,
) -> dict[str, Any]:
    """Register a backgrounded main session task.

    Called when the user backgrounds the current session query.

    Args:
        description: Description of the task
        set_app_state: State setter function
        main_thread_agent_definition: Optional agent definition if running with --agent
        existing_abort_controller: Optional abort controller to reuse

    Returns:
        Dict with task_id and abort_signal
    """
    task_id = _generate_main_session_task_id()

    # Link output to an isolated per-task transcript file
    asyncio.ensure_future(
        init_task_output_as_symlink(
            task_id,
            get_agent_transcript_path(task_id),
        )
    )

    # Use the existing abort controller if provided
    abort_controller = existing_abort_controller or create_abort_controller()

    def cleanup():
        set_app_state(lambda prev: {
            **prev,
            "tasks": {k: v for k, v in prev.get("tasks", {}).items() if k != task_id},
        })

    unregister_cleanup = register_cleanup(cleanup)

    selected_agent = main_thread_agent_definition or DEFAULT_MAIN_SESSION_AGENT

    task_state = LocalMainSessionTaskState(
        **create_task_state_base(task_id, "local_agent", description),
        type="local_agent",
        status="running",
        agent_id=task_id,
        prompt=description,
        selected_agent=selected_agent,
        agent_type="main-session",
        abort_controller=abort_controller,
        unregister_cleanup=unregister_cleanup,
        retrieved=False,
        last_reported_tool_count=0,
        last_reported_token_count=0,
        is_backgrounded=True,
        pending_messages=[],
        retain=False,
        disk_loaded=False,
    )

    log_for_debugging(
        f"[LocalMainSessionTask] Registering task {task_id} with description: {description}"
    )
    register_task(task_state, set_app_state)

    # Verify task was registered
    def verify(prev: dict) -> dict:
        has_task = task_id in prev.get("tasks", {})
        log_for_debugging(
            f"[LocalMainSessionTask] After registration, task {task_id} exists in state: {has_task}"
        )
        return prev

    set_app_state(verify)

    return {"task_id": task_id, "abort_signal": abort_controller.signal}


def complete_main_session_task(
    task_id: str,
    success: bool,
    set_app_state: "SetAppState",
) -> None:
    """Complete the main session task and send notification.

    Called when the backgrounded query finishes.
    """
    was_backgrounded = True
    tool_use_id: Optional[str] = None

    def update_fn(task: LocalMainSessionTaskState) -> LocalMainSessionTaskState:
        nonlocal was_backgrounded, tool_use_id
        if task.status != "running":
            return task

        was_backgrounded = getattr(task, "is_backgrounded", True)
        tool_use_id = getattr(task, "tool_use_id", None)

        if task.unregister_cleanup:
            task.unregister_cleanup()

        messages = getattr(task, "messages", None)
        last_msg = [messages[-1]] if messages else None

        return LocalMainSessionTaskState(
            **{
                **vars(task),
                "status": "completed" if success else "failed",
                "end_time": _now_ms(),
                "messages": last_msg,
            }
        )

    update_task_state(task_id, set_app_state, update_fn)
    asyncio.ensure_future(evict_task_output(task_id))

    if was_backgrounded:
        _enqueue_main_session_notification(
            task_id,
            "Background session",
            "completed" if success else "failed",
            set_app_state,
            tool_use_id,
        )
    else:
        # Foregrounded: no XML notification, but SDK consumers still need the bookend
        def set_notified(task):
            return LocalMainSessionTaskState(**{**vars(task), "notified": True})

        update_task_state(task_id, set_app_state, set_notified)
        emit_task_terminated_sdk(
            task_id,
            "completed" if success else "failed",
            tool_use_id=tool_use_id,
            summary="Background session",
        )


def _enqueue_main_session_notification(
    task_id: str,
    description: str,
    status: str,
    set_app_state: "SetAppState",
    tool_use_id: Optional[str] = None,
) -> None:
    """Enqueue a notification about the backgrounded session completing."""
    should_enqueue = False

    def check_and_set(task):
        nonlocal should_enqueue
        if getattr(task, "notified", False):
            return task
        should_enqueue = True
        return LocalMainSessionTaskState(**{**vars(task), "notified": True})

    update_task_state(task_id, set_app_state, check_and_set)

    if not should_enqueue:
        return

    summary = (
        f'Background session "{description}" completed'
        if status == "completed"
        else f'Background session "{description}" failed'
    )

    tool_use_id_line = (
        f"\n<{TOOL_USE_ID_TAG}>{tool_use_id}</{TOOL_USE_ID_TAG}>"
        if tool_use_id
        else ""
    )

    output_path = get_task_output_path(task_id)
    message = (
        f"<{TASK_NOTIFICATION_TAG}>\n"
        f"<{TASK_ID_TAG}>{task_id}</{TASK_ID_TAG}>{tool_use_id_line}\n"
        f"<{OUTPUT_FILE_TAG}>{output_path}</{OUTPUT_FILE_TAG}>\n"
        f"<{STATUS_TAG}>{status}</{STATUS_TAG}>\n"
        f"<{SUMMARY_TAG}>{summary}</{SUMMARY_TAG}>\n"
        f"</{TASK_NOTIFICATION_TAG}>"
    )

    enqueue_pending_notification({"value": message, "mode": "task-notification"})


def foreground_main_session_task(
    task_id: str,
    set_app_state: "SetAppState",
) -> Optional[list["Message"]]:
    """Foreground a main session task.

    Returns the task's accumulated messages, or None if task not found.
    """
    task_messages: Optional[list] = None

    def update_fn(prev: dict) -> dict:
        nonlocal task_messages
        task = prev.get("tasks", {}).get(task_id)
        if not task or getattr(task, "type", None) != "local_agent":
            return prev

        task_messages = getattr(task, "messages", None)

        # Restore previous foregrounded task to background if it exists
        prev_id = prev.get("foregrounded_task_id")
        prev_task = prev.get("tasks", {}).get(prev_id) if prev_id else None
        restore_prev = (
            prev_id
            and prev_id != task_id
            and prev_task
            and getattr(prev_task, "type", None) == "local_agent"
        )

        updated_tasks = dict(prev.get("tasks", {}))
        if restore_prev:
            updated_tasks[prev_id] = LocalMainSessionTaskState(
                **{**vars(prev_task), "is_backgrounded": True}
            )
        updated_tasks[task_id] = LocalMainSessionTaskState(
            **{**vars(task), "is_backgrounded": False}
        )

        return {
            **prev,
            "foregrounded_task_id": task_id,
            "tasks": updated_tasks,
        }

    set_app_state(update_fn)
    return task_messages


def is_main_session_task(task: Any) -> bool:
    """Check if a task is a main session task (vs a regular agent task)."""
    if not isinstance(task, dict) and not hasattr(task, "__dict__"):
        return False
    task_type = task.get("type") if isinstance(task, dict) else getattr(task, "type", None)
    agent_type = task.get("agent_type") if isinstance(task, dict) else getattr(task, "agent_type", None)
    return task_type == "local_agent" and agent_type == "main-session"


def start_background_session(
    messages: list["Message"],
    query_params: "QueryParams",
    description: str,
    set_app_state: "SetAppState",
    agent_definition: Optional["AgentDefinition"] = None,
) -> str:
    """Start a fresh background session with the given messages.

    Spawns an independent query() call with the current messages and registers
    it as a background task.

    Returns:
        task_id of the newly started background session
    """
    from ...query import query as run_query

    result = register_main_session_task(
        description,
        set_app_state,
        agent_definition,
    )
    task_id = result["task_id"]
    abort_signal = result["abort_signal"]

    # Persist the pre-backgrounding conversation to the task's isolated transcript
    asyncio.ensure_future(
        record_sidechain_transcript(messages, task_id)
    )

    agent_context = SubagentContext(
        agent_id=task_id,
        agent_type="subagent",
        subagent_name="main-session",
        is_built_in=True,
    )

    async def _run_bg():
        try:
            bg_messages = list(messages)
            recent_activities: list[dict] = []
            tool_count = 0
            token_count = 0
            last_recorded_uuid = messages[-1].get("uuid") if messages else None

            async for event in run_query(messages=bg_messages, **query_params):
                if getattr(abort_signal, "aborted", False):
                    already_notified = False

                    def check_notified(task):
                        nonlocal already_notified
                        already_notified = getattr(task, "notified", False)
                        return task if already_notified else LocalMainSessionTaskState(
                            **{**vars(task), "notified": True}
                        )

                    update_task_state(task_id, set_app_state, check_notified)
                    if not already_notified:
                        emit_task_terminated_sdk(task_id, "stopped", summary=description)
                    return

                event_type = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
                if event_type not in ("user", "assistant", "system"):
                    continue

                bg_messages.append(event)

                asyncio.ensure_future(
                    record_sidechain_transcript([event], task_id, last_recorded_uuid)
                )
                last_recorded_uuid = event.get("uuid") if isinstance(event, dict) else getattr(event, "uuid", None)

                if event_type == "assistant":
                    content = event.get("message", {}).get("content", []) if isinstance(event, dict) else []
                    for block in content:
                        block_type = block.get("type") if isinstance(block, dict) else None
                        if block_type == "text":
                            token_count += rough_token_count_estimation(block.get("text", ""))
                        elif block_type == "tool_use":
                            tool_count += 1
                            recent_activities.append({
                                "toolName": block.get("name"),
                                "input": block.get("input", {}),
                            })
                            if len(recent_activities) > _MAX_RECENT_ACTIVITIES:
                                recent_activities.pop(0)

                def update_progress(prev: dict) -> dict:
                    task = prev.get("tasks", {}).get(task_id)
                    if not task or getattr(task, "type", None) != "local_agent":
                        return prev
                    prev_progress = getattr(task, "progress", None)
                    if (
                        prev_progress
                        and prev_progress.get("tokenCount") == token_count
                        and prev_progress.get("toolUseCount") == tool_count
                        and getattr(task, "messages", None) is bg_messages
                    ):
                        return prev

                    same_tool_count = (
                        prev_progress and prev_progress.get("toolUseCount") == tool_count
                    )
                    updated_tasks = dict(prev.get("tasks", {}))
                    updated_tasks[task_id] = type(task)(**{
                        **vars(task),
                        "progress": {
                            "tokenCount": token_count,
                            "toolUseCount": tool_count,
                            "recentActivities": (
                                prev_progress.get("recentActivities", [])
                                if same_tool_count and prev_progress
                                else list(recent_activities)
                            ),
                        },
                        "messages": bg_messages,
                    })
                    return {**prev, "tasks": updated_tasks}

                set_app_state(update_progress)

            complete_main_session_task(task_id, True, set_app_state)
        except Exception as error:
            log_error(error)
            complete_main_session_task(task_id, False, set_app_state)

    asyncio.ensure_future(run_with_agent_context(agent_context, _run_bg()))

    return task_id


def _now_ms() -> int:
    """Return current time in milliseconds."""
    import time
    return int(time.time() * 1000)
