"""TaskGetTool package.

Re-exports TaskGetTool and its canonical name constant.

TaskGetTool retrieves a single task by ID from the shared task list,
returning its full description, status, dependencies, and any additional
metadata.  Use this before starting work on a task to get complete context.

Ported from: tools/TaskGetTool/ (TypeScript)

Usage::

    from claude_code.tools.task_get_tool import TaskGetTool, TASK_GET_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.task_get_tool.task_get_tool import TaskGetTool
from claude_code.tools.task_get_tool.constants import TASK_GET_TOOL_NAME

__all__ = [
    "TaskGetTool",
    "TASK_GET_TOOL_NAME",
]
