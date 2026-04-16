"""Task get tool. Ported from TaskGetTool/taskGetTool.ts"""
from __future__ import annotations
from typing import Any

TASK_GET_TOOL_NAME = "TaskGet"
DESCRIPTION = "Get a task by ID from the task list"
PROMPT = """Use this tool to retrieve a task by its ID from the task list."""


class TaskGetTool:
    name = TASK_GET_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The ID of the task to retrieve"}
                },
                "required": ["task_id"]
            }
        }

    async def call(self, task_id: str, **kwargs: Any) -> dict:
        from claude_code.services.task_manager import get_task_manager
        tm = get_task_manager()
        task = tm.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}
        return task
