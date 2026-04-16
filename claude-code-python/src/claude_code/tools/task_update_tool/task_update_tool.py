"""TaskUpdate tool. Ported from TaskUpdateTool."""
from __future__ import annotations
from typing import Any, List, Optional

TASK_UPDATE_TOOL_NAME = "TaskUpdate"
DESCRIPTION = "Update a task in the task list"
PROMPT = """Use this tool to update a task in the task list.

Status progresses: `pending` → `in_progress` → `completed`
Use `deleted` to permanently remove a task."""


class TaskUpdateTool:
    name = TASK_UPDATE_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "taskId": {"type": "string", "description": "ID of task to update"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]},
                    "subject": {"type": "string"},
                    "description": {"type": "string"},
                    "owner": {"type": "string"},
                    "addBlocks": {"type": "array", "items": {"type": "string"}},
                    "addBlockedBy": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["taskId"]
            }
        }

    async def call(self, taskId: str, status: Optional[str] = None,
                   subject: Optional[str] = None, description: Optional[str] = None,
                   owner: Optional[str] = None, addBlocks: Optional[List[str]] = None,
                   addBlockedBy: Optional[List[str]] = None, **kwargs: Any) -> dict:
        from claude_code.services.task_manager import get_task_manager
        tm = get_task_manager()
        updates = {k: v for k, v in {
            "status": status, "subject": subject,
            "description": description, "owner": owner,
        }.items() if v is not None}
        task = tm.update_task(taskId, updates, add_blocks=addBlocks, add_blocked_by=addBlockedBy)
        if not task:
            return {"error": f"Task {taskId} not found"}
        return task
