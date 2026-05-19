"""Task utilities.

Provides task state management, output formatting, and progress-tracking
helpers used by the Task (Agent) tool and the background-task subsystem.

Ported from: src/utils/task/ (TypeScript)

Usage::

    from claude_code.utils.task import TaskAttachment, TaskOutput, register_task
"""
from __future__ import annotations

from claude_code.utils.task.framework import (
    TaskAttachment,
    register_task,
)
from claude_code.utils.task.task_output import TaskOutput

__all__ = [
    "TaskAttachment",
    "TaskOutput",
    "register_task",
]
