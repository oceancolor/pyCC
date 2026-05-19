"""TaskStopTool package.

Re-exports TaskStopTool and its canonical name constant.

TaskStopTool terminates a running background task by ID.  It can be used
when a task is no longer needed, has errored unrecoverably, or needs to be
restarted with different parameters.

Ported from: tools/TaskStopTool/ (TypeScript)

Usage::

    from claude_code.tools.task_stop_tool import TaskStopTool, TASK_STOP_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.task_stop_tool.task_stop_tool import TaskStopTool
from claude_code.tools.task_stop_tool.prompt import TASK_STOP_TOOL_NAME

__all__ = [
    "TaskStopTool",
    "TASK_STOP_TOOL_NAME",
]
