"""Task utilities sub-package. Ported from utils/task/.

Provides task state management, output formatting, and progress tracking
helpers for the Task (agent) tool.
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
