"""SDK progress event utilities. Ported from utils/task/sdkProgress.ts"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable


@dataclass
class SdkWorkflowProgress:
    """Progress update for an SDK-driven workflow task."""

    task_id: str
    """Unique identifier for this task."""
    status: str
    """Current status: 'pending' | 'running' | 'complete' | 'error'."""
    message: Optional[str] = None
    """Human-readable status message."""
    percent: Optional[float] = None
    """Completion percentage 0–100, if known."""
    metadata: Dict[str, Any] = field(default_factory=dict)
    """Arbitrary structured metadata for the UI."""

    def to_dict(self) -> dict:
        d: dict = {
            "taskId": self.task_id,
            "status": self.status,
        }
        if self.message is not None:
            d["message"] = self.message
        if self.percent is not None:
            d["percent"] = self.percent
        if self.metadata:
            d["metadata"] = self.metadata
        return d


# Module-level queue of pending SDK events (drained by the SDK event loop).
_sdk_event_queue: List[SdkWorkflowProgress] = []
_sdk_event_listeners: List[Callable[[SdkWorkflowProgress], None]] = []


def enqueue_sdk_progress_event(event: SdkWorkflowProgress) -> None:
    """Add a workflow progress event to the queue and notify listeners."""
    _sdk_event_queue.append(event)
    for listener in list(_sdk_event_listeners):
        try:
            listener(event)
        except Exception:
            pass


def subscribe_sdk_progress(
    listener: Callable[[SdkWorkflowProgress], None]
) -> Callable[[], None]:
    """Subscribe to SDK progress events.

    Returns an unsubscribe function that removes the listener.
    """
    _sdk_event_listeners.append(listener)

    def unsubscribe() -> None:
        try:
            _sdk_event_listeners.remove(listener)
        except ValueError:
            pass

    return unsubscribe


def drain_sdk_event_queue() -> List[SdkWorkflowProgress]:
    """Remove and return all queued SDK progress events."""
    events = list(_sdk_event_queue)
    _sdk_event_queue.clear()
    return events


def create_progress_event(
    task_id: str,
    status: str,
    message: Optional[str] = None,
    percent: Optional[float] = None,
    **metadata: Any,
) -> SdkWorkflowProgress:
    """Convenience constructor for :class:`SdkWorkflowProgress`."""
    return SdkWorkflowProgress(
        task_id=task_id,
        status=status,
        message=message,
        percent=percent,
        metadata=metadata,
    )
