"""TaskListTool constants.

Ported from: tools/TaskListTool/constants.ts

Defines the canonical API-level tool name used to identify the
TaskList tool in tool-use messages and permission rules.

TaskList returns a summary of all tasks in the shared task list, showing
each task's ID, title, status, and assignee.  Use this before creating new
tasks or assigning teammates to get an overview of outstanding work.

See also
--------
``claude_code.tools.task_list_tool.task_list_tool`` : Implementation.
``claude_code.tools.task_create_tool.constants`` : Related TaskCreate name.
``claude_code.tools.task_get_tool.constants`` : Related TaskGet name.
"""
from __future__ import annotations

#: The API-level tool name used to identify the TaskList tool.
TASK_LIST_TOOL_NAME: str = "TaskList"

__all__ = ["TASK_LIST_TOOL_NAME"]
