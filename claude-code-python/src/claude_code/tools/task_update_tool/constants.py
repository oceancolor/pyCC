"""TaskUpdateTool constants.

Ported from: tools/TaskUpdateTool/constants.ts

Defines the canonical API-level tool name used to identify the
TaskUpdate tool in tool-use messages and permission rules.

TaskUpdate modifies an existing task in the shared task list.  Common
use cases include marking a task as resolved when the work is complete,
updating the description with new information, or changing the task
priority or assignee.

See also
--------
``claude_code.tools.task_update_tool.task_update_tool`` : Implementation.
``claude_code.tools.task_create_tool.constants`` : Related TaskCreate name.
"""
from __future__ import annotations

#: The API-level tool name used to identify the TaskUpdate tool.
TASK_UPDATE_TOOL_NAME: str = "TaskUpdate"

__all__ = ["TASK_UPDATE_TOOL_NAME"]
