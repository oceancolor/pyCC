"""
Task state union types.
Ported from tasks/types.ts
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Union


# TaskState and BackgroundTaskState are structural unions — we model them as
# plain dicts at runtime since full TypedDict hierarchies for every task type
# would require circular imports.  Use `typing.Any` where the concrete type
# isn't needed.
TaskState = Any
BackgroundTaskState = Any


def is_background_task(task: Dict[str, Any]) -> bool:
    """Return True if the task should be shown in the background tasks indicator.

    A task is a background task when:
    1. Its status is 'running' or 'pending'
    2. It has not been explicitly kept in the foreground (isBackgrounded != False)

    Mirrors ``isBackgroundTask`` from tasks/types.ts.
    """
    status = task.get("status") or task.get("status")
    if status not in ("running", "pending"):
        return False
    # Foreground tasks have isBackgrounded == False
    if "isBackgrounded" in task and task["isBackgrounded"] is False:
        return False
    return True
