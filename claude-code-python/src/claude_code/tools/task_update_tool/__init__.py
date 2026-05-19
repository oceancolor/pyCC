"""TaskUpdateTool package.

Re-exports TaskUpdateTool and its canonical name constant.

TaskUpdateTool modifies an existing task in the shared task list.
Use it to update the task status (e.g. mark as resolved), change the
description, or update dependencies.

Ported from: tools/TaskUpdateTool/ (TypeScript)

Usage::

    from claude_code.tools.task_update_tool import TaskUpdateTool, TASK_UPDATE_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.task_update_tool.task_update_tool import TaskUpdateTool
from claude_code.tools.task_update_tool.constants import TASK_UPDATE_TOOL_NAME

__all__ = [
    "TaskUpdateTool",
    "TASK_UPDATE_TOOL_NAME",
]
