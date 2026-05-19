"""TaskGetTool constants.

Ported from: tools/TaskGetTool/constants.ts

Defines the canonical API-level tool name used to identify the
TaskGet tool in tool-use messages and permission rules.

TaskGet retrieves a single task by ID from the shared task list, returning
its full description, status, dependencies, and any additional metadata.
It is the complement to TaskList: use TaskList for an overview and TaskGet
for full details before starting work.

See also
--------
``claude_code.tools.task_get_tool.task_get_tool`` : Implementation.
``claude_code.tools.task_list_tool.constants`` : Related TaskList name.
"""
from __future__ import annotations

#: The API-level tool name used to identify the TaskGet tool.
TASK_GET_TOOL_NAME: str = "TaskGet"

__all__ = ["TASK_GET_TOOL_NAME"]
