"""Task stop tool. Ported from TaskStopTool."""
from __future__ import annotations
from typing import Any

TASK_STOP_TOOL_NAME = "TaskStop"
DESCRIPTION = "Stops a running background task by its ID"


class TaskStopTool:
    name = TASK_STOP_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The ID of the task to stop"}
                },
                "required": ["task_id"]
            }
        }

    async def call(self, task_id: str, **kwargs: Any) -> dict:
        from claude_code.services.task_manager import get_task_manager
        tm = get_task_manager()
        success = tm.stop_task(task_id)
        return {"success": success, "task_id": task_id}
