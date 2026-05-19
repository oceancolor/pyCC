"""TaskCreateTool package.

Re-exports TaskCreateTool and its canonical name constant.

TaskCreateTool adds a new task entry to the shared task list.  In swarm
mode the task can also be assigned to a teammate agent for parallel
execution.

Ported from: tools/TaskCreateTool/ (TypeScript)

Usage::

    from claude_code.tools.task_create_tool import TaskCreateTool, TASK_CREATE_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.task_create_tool.task_create_tool import TaskCreateTool
from claude_code.tools.task_create_tool.constants import TASK_CREATE_TOOL_NAME

__all__ = [
    "TaskCreateTool",
    "TASK_CREATE_TOOL_NAME",
]
