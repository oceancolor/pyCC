"""
SDK event queue for streaming / headless mode.

Mirrors TypeScript sdkEventQueue.ts. Events are enqueued by producers
(tool execution, task management) and drained by the output stream layer.

Only operates in non-interactive (headless) sessions; enqueue() is a no-op
in interactive mode so events never accumulate.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union

# Maximum number of events held before oldest is dropped
MAX_QUEUE_SIZE = 1000


# ---------------------------------------------------------------------------
# Event type definitions
# ---------------------------------------------------------------------------

@dataclass
class TaskStartedEvent:
    type: Literal["system"] = "system"
    subtype: Literal["task_started"] = "task_started"
    task_id: str = ""
    tool_use_id: Optional[str] = None
    description: str = ""
    task_type: Optional[str] = None
    workflow_name: Optional[str] = None
    prompt: Optional[str] = None


@dataclass
class TaskUsage:
    total_tokens: int = 0
    tool_uses: int = 0
    duration_ms: int = 0


@dataclass
class TaskProgressEvent:
    type: Literal["system"] = "system"
    subtype: Literal["task_progress"] = "task_progress"
    task_id: str = ""
    tool_use_id: Optional[str] = None
    description: str = ""
    usage: TaskUsage = field(default_factory=TaskUsage)
    last_tool_name: Optional[str] = None
    summary: Optional[str] = None
    workflow_progress: Optional[list[Any]] = None


@dataclass
class TaskNotificationEvent:
    type: Literal["system"] = "system"
    subtype: Literal["task_notification"] = "task_notification"
    task_id: str = ""
    tool_use_id: Optional[str] = None
    status: Literal["completed", "failed", "stopped"] = "completed"
    output_file: str = ""
    summary: str = ""
    usage: Optional[TaskUsage] = None


@dataclass
class SessionStateChangedEvent:
    type: Literal["system"] = "system"
    subtype: Literal["session_state_changed"] = "session_state_changed"
    state: Literal["idle", "running", "requires_action"] = "idle"


SdkEvent = Union[
    TaskStartedEvent,
    TaskProgressEvent,
    TaskNotificationEvent,
    SessionStateChangedEvent,
]


# ---------------------------------------------------------------------------
# Module-level queue state
# ---------------------------------------------------------------------------

_queue: list[SdkEvent] = []


def _is_non_interactive() -> bool:
    val = os.environ.get("CLAUDE_CODE_NON_INTERACTIVE", "")
    return val.lower() in ("1", "true", "yes")


def enqueue_sdk_event(event: SdkEvent) -> None:
    """
    Append *event* to the internal queue.

    No-op in interactive (TUI) mode to avoid unbounded accumulation.
    Drops the oldest event when the queue reaches MAX_QUEUE_SIZE.
    """
    if not _is_non_interactive():
        return
    if len(_queue) >= MAX_QUEUE_SIZE:
        _queue.pop(0)
    _queue.append(event)


def drain_sdk_events(session_id: str = "") -> list[dict]:
    """
    Remove and return all queued events, each annotated with a uuid and session_id.

    Returns:
        List of dicts with all event fields plus ``uuid`` and ``session_id``.
    """
    if not _queue:
        return []
    events = _queue[:]
    _queue.clear()
    result = []
    for event in events:
        d = vars(event).copy()
        d["uuid"] = str(uuid.uuid4())
        d["session_id"] = session_id
        result.append(d)
    return result


def emit_task_terminated(
    task_id: str,
    status: Literal["completed", "failed", "stopped"],
    *,
    tool_use_id: Optional[str] = None,
    summary: str = "",
    output_file: str = "",
    usage: Optional[TaskUsage] = None,
) -> None:
    """Enqueue a task_notification event marking a task as terminal."""
    enqueue_sdk_event(
        TaskNotificationEvent(
            task_id=task_id,
            tool_use_id=tool_use_id,
            status=status,
            output_file=output_file,
            summary=summary,
            usage=usage,
        )
    )


# ---------------------------------------------------------------------------
# Async queue wrapper (for consumers that prefer asyncio.Queue)
# ---------------------------------------------------------------------------

class SdkEventQueue:
    """
    asyncio.Queue-backed wrapper for SDK events.

    Suitable for async producers/consumers. For simple sync use,
    prefer the module-level enqueue_sdk_event / drain_sdk_events.
    """

    def __init__(self, maxsize: int = MAX_QUEUE_SIZE) -> None:
        self._q: asyncio.Queue[SdkEvent] = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, event: SdkEvent) -> None:
        """Put an event; drops oldest if full (non-blocking)."""
        if self._q.full():
            try:
                self._q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self._q.put(event)

    async def dequeue(self) -> SdkEvent:
        """Wait for and return the next event."""
        return await self._q.get()

    async def drain(self) -> list[SdkEvent]:
        """Return all currently queued events without waiting."""
        items: list[SdkEvent] = []
        while not self._q.empty():
            try:
                items.append(self._q.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items
