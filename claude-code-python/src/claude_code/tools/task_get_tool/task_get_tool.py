"""Task get tool. Ported from TaskGetTool/TaskGetTool.ts."""
from __future__ import annotations

from typing import Any, List, Optional

TASK_GET_TOOL_NAME = "TaskGet"
DESCRIPTION = "Retrieve a task by its ID from the task list"
PROMPT = "Use this tool to retrieve a task by its ID from the task list."


class TaskGetTool:
    """Fetch a single task entry from the task list by ID.

    Mirrors the TS ``TaskGetTool.call`` which calls ``getTask(taskListId, taskId)``
    and returns the full task object or null.
    """

    name = TASK_GET_TOOL_NAME
    description = DESCRIPTION
    should_defer = True
    is_concurrency_safe = True
    is_read_only = True

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "taskId": {
                        "type": "string",
                        "description": "The ID of the task to retrieve",
                    }
                },
                "required": ["taskId"],
            },
        }

    async def call(self, taskId: str, **kwargs: Any) -> dict:  # noqa: N803
        from claude_code.services.task_manager import get_task_manager

        tm = get_task_manager()
        task = tm.get_task(taskId)
        if not task:
            return {"task": None}

        return {
            "task": {
                "id": task["id"],
                "subject": task.get("subject", ""),
                "description": task.get("description", ""),
                "status": task.get("status", "pending"),
                "blocks": task.get("blocks", []),
                "blockedBy": task.get("blocked_by", []),
            }
        }

    def map_tool_result(self, content: dict, tool_use_id: str) -> dict:
        task = content.get("task")
        if not task:
            text = "Task not found"
        else:
            lines = [
                f"Task #{task['id']}: {task['subject']}",
                f"Status: {task['status']}",
                f"Description: {task.get('description', '')}",
            ]
            blocked_by: List[str] = task.get("blockedBy", [])
            blocks: List[str] = task.get("blocks", [])
            if blocked_by:
                lines.append("Blocked by: " + ", ".join(f"#{i}" for i in blocked_by))
            if blocks:
                lines.append("Blocks: " + ", ".join(f"#{i}" for i in blocks))
            text = "\n".join(lines)

        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": text,
        }
