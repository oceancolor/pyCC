"""TaskCreateTool constants.

Ported from: tools/TaskCreateTool/constants.ts

Defines the canonical API-level tool name used to identify the
TaskCreate tool in tool-use messages and permission rules.

TaskCreate adds a new entry to the shared task list.  In agent-swarm mode
tasks can also be assigned to teammate agents for parallel execution.
Keeping the name in a separate constants module avoids circular imports
between the tool class and the task management subsystem.

See also
--------
``claude_code.tools.task_create_tool.task_create_tool`` : Implementation.
``claude_code.tools.task_list_tool.constants`` : Related TaskList name.
"""
from __future__ import annotations

#: The API-level tool name used to identify the TaskCreate tool.
TASK_CREATE_TOOL_NAME: str = "TaskCreate"

__all__ = ["TASK_CREATE_TOOL_NAME"]
