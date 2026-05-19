"""TaskStopTool prompt constants.

Ported from: tools/TaskStopTool/prompt.ts

Contains the tool name and description string used to register
TaskStopTool in the tool catalogue.
"""
from __future__ import annotations

#: The API-level tool name used to identify the TaskStop tool.
TASK_STOP_TOOL_NAME: str = "TaskStop"

#: Multi-line description shown in the tool catalogue.
DESCRIPTION: str = (
    "- Stops a running background task by its ID\n"
    "- Takes a task_id parameter identifying the task to stop\n"
    "- Returns a success or failure status\n"
    "- Use this tool when you need to terminate a long-running task"
)

__all__ = ["TASK_STOP_TOOL_NAME", "DESCRIPTION"]
