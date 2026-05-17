"""RemoteAgentTask. Ported from tasks/RemoteAgentTask/RemoteAgentTask.tsx."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Remote task type literals
# ---------------------------------------------------------------------------

REMOTE_TASK_TYPES = ("remote-agent", "ultraplan", "ultrareview", "autofix-pr", "background-pr")
RemoteTaskType = str  # one of REMOTE_TASK_TYPES


def is_remote_task_type(v: Optional[str]) -> bool:
    return v in REMOTE_TASK_TYPES


# ---------------------------------------------------------------------------
# State type
# ---------------------------------------------------------------------------

@dataclass
class ReviewProgress:
    stage: Optional[str] = None  # 'finding' | 'verifying' | 'synthesizing'
    bugs_found: int = 0
    bugs_verified: int = 0
    bugs_refuted: int = 0


@dataclass
class RemoteAgentTaskState:
    """
    State for a remote agent task.
    Mirrors ``RemoteAgentTaskState`` from RemoteAgentTask.tsx.
    """
    id: str
    type: str = "remote_agent"
    remote_task_type: RemoteTaskType = "remote-agent"
    remote_task_metadata: Optional[Dict[str, Any]] = None
    session_id: str = ""
    command: str = ""
    title: str = ""
    description: str = ""
    todo_list: List[Any] = field(default_factory=list)
    log: List[Any] = field(default_factory=list)
    is_long_running: Optional[bool] = None
    poll_started_at: float = field(default_factory=lambda: time.time() * 1000)
    is_remote_review: Optional[bool] = None
    review_progress: Optional[ReviewProgress] = None
    is_ultraplan: Optional[bool] = None
    ultraplan_phase: Optional[str] = None
    status: str = "running"
    start_time: float = field(default_factory=lambda: time.time() * 1000)
    end_time: Optional[float] = None
    notified: bool = False
    tool_use_id: Optional[str] = None
    output_file: str = ""
    output_offset: int = 0


def is_remote_agent_task(task: Any) -> bool:
    """Return True if *task* is a RemoteAgentTaskState."""
    if isinstance(task, dict):
        return task.get("type") == "remote_agent"
    return getattr(task, "type", None) == "remote_agent"


# ---------------------------------------------------------------------------
# Completion checkers registry
# ---------------------------------------------------------------------------

_completion_checkers: Dict[RemoteTaskType, Callable] = {}


def register_completion_checker(remote_task_type: RemoteTaskType, checker: Callable) -> None:
    """
    Register a completion checker for a remote task type.
    Mirrors ``registerCompletionChecker`` from the TS source.
    """
    _completion_checkers[remote_task_type] = checker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mark_task_notified(task_id: str, set_app_state: Callable) -> bool:
    """
    Atomically set notified=True. Returns True if this call flipped the flag.
    """
    should_enqueue = [False]

    def _update(prev: dict) -> dict:
        tasks = dict(prev.get("tasks") or {})
        task = tasks.get(task_id)
        if task is None:
            return prev
        already = task.get("notified") if isinstance(task, dict) else getattr(task, "notified", False)
        if already:
            return prev
        should_enqueue[0] = True
        if isinstance(task, dict):
            tasks[task_id] = {**task, "notified": True}
        else:
            tasks[task_id] = RemoteAgentTaskState(**{**task.__dict__, "notified": True})
        return {**prev, "tasks": tasks}

    set_app_state(_update)
    return should_enqueue[0]


def _enqueue_remote_notification(
    task_id: str,
    title: str,
    status: str,
    set_app_state: Callable,
    tool_use_id: Optional[str] = None,
) -> None:
    """Enqueue a remote task notification. Mirrors ``enqueueRemoteNotification``."""
    if not _mark_task_notified(task_id, set_app_state):
        return

    try:
        from claude_code.constants.xml import (  # type: ignore[import]
            OUTPUT_FILE_TAG, STATUS_TAG, SUMMARY_TAG, TASK_ID_TAG,
            TASK_NOTIFICATION_TAG, TASK_TYPE_TAG, TOOL_USE_ID_TAG,
        )
        from claude_code.utils.task.disk_output import get_task_output_path  # type: ignore[import]
        from claude_code.utils.message_queue_manager import enqueue_pending_notification  # type: ignore[import]
    except ImportError:
        return

    status_text = (
        "completed successfully" if status == "completed"
        else "failed" if status == "failed"
        else "was stopped"
    )
    tool_use_id_line = (
        f"\n<{TOOL_USE_ID_TAG}>{tool_use_id}</{TOOL_USE_ID_TAG}>"
        if tool_use_id else ""
    )
    output_path = get_task_output_path(task_id)
    message = (
        f"<{TASK_NOTIFICATION_TAG}>\n"
        f"<{TASK_ID_TAG}>{task_id}</{TASK_ID_TAG}>{tool_use_id_line}\n"
        f"<{TASK_TYPE_TAG}>remote_agent</{TASK_TYPE_TAG}>\n"
        f"<{OUTPUT_FILE_TAG}>{output_path}</{OUTPUT_FILE_TAG}>\n"
        f"<{STATUS_TAG}>{status}</{STATUS_TAG}>\n"
        f'<{SUMMARY_TAG}>Remote task "{title}" {status_text}</{SUMMARY_TAG}>\n'
        f"</{TASK_NOTIFICATION_TAG}>"
    )
    enqueue_pending_notification({"value": message, "mode": "task-notification"})


# ---------------------------------------------------------------------------
# Task descriptor
# ---------------------------------------------------------------------------

class RemoteAgentTask:
    """
    Task descriptor for remote agent tasks.
    Mirrors ``RemoteAgentTask`` from RemoteAgentTask.tsx.
    """
    type = "remote_agent"
    name = "RemoteAgentTask"

    @classmethod
    async def kill(cls, task_id: str, set_app_state: Callable) -> None:
        """
        Kill a running RemoteAgentTask.

        - Marks status as 'killed', notified=True.
        - Emits SDK task-terminated event.
        - Archives the remote session so it stops consuming cloud resources.
        - Evicts task output.
        - Removes remote agent metadata from the session sidecar.

        Mirrors ``RemoteAgentTask.kill`` from RemoteAgentTask.tsx.
        """
        tool_use_id: Optional[str] = None
        description: Optional[str] = None
        session_id: Optional[str] = None
        killed = False

        def _update(prev: dict) -> dict:
            nonlocal tool_use_id, description, session_id, killed
            tasks = dict(prev.get("tasks") or {})
            task = tasks.get(task_id)
            if task is None:
                return prev

            if isinstance(task, RemoteAgentTaskState):
                if task.status != "running":
                    return prev
                tool_use_id = task.tool_use_id
                description = task.description
                session_id = task.session_id
                killed = True
                tasks[task_id] = RemoteAgentTaskState(
                    **{**task.__dict__,
                       "status": "killed",
                       "notified": True,
                       "end_time": time.time() * 1000}
                )
            elif isinstance(task, dict):
                if task.get("status") != "running":
                    return prev
                tool_use_id = task.get("tool_use_id")
                description = task.get("description")
                session_id = task.get("session_id")
                killed = True
                tasks[task_id] = {
                    **task,
                    "status": "killed",
                    "notified": True,
                    "end_time": time.time() * 1000,
                }
            return {**prev, "tasks": tasks}

        set_app_state(_update)

        if not killed:
            return

        # Emit SDK task-terminated event
        try:
            from claude_code.utils.sdk_event_queue import emit_task_terminated_sdk  # type: ignore[import]
            emit_task_terminated_sdk(task_id, "stopped", tool_use_id=tool_use_id, summary=description)
        except (ImportError, Exception) as exc:
            logger.debug("emit_task_terminated_sdk skipped: %s", exc)

        # Archive the remote session
        if session_id:
            try:
                from claude_code.utils.teleport import archive_remote_session  # type: ignore[import]
                asyncio.ensure_future(
                    archive_remote_session(session_id),
                    # Note: exceptions are swallowed per TS original
                )
            except (ImportError, Exception) as exc:
                logger.debug("archive_remote_session skipped: %s", exc)

        # Evict task output
        try:
            from claude_code.utils.task.disk_output import evict_task_output  # type: ignore[import]
            asyncio.ensure_future(evict_task_output(task_id))
        except (ImportError, Exception):
            pass

        # Remove metadata sidecar entry
        try:
            from claude_code.utils.session_storage import delete_remote_agent_metadata  # type: ignore[import]
            asyncio.ensure_future(delete_remote_agent_metadata(task_id))
        except (ImportError, Exception):
            pass

        logger.debug(
            "RemoteAgentTask %s killed, archiving session %s",
            task_id, session_id or "unknown",
        )
