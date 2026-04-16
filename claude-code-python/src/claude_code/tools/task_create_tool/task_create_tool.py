"""Task create tool. Ported from TaskCreateTool."""
from __future__ import annotations
from typing import Any, Optional
from claude_code.utils.agent_swarms_enabled import is_agent_swarms_enabled

TASK_CREATE_TOOL_NAME = "TaskCreate"
DESCRIPTION = "Create a new task in the task list"


class TaskCreateTool:
    name = TASK_CREATE_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Brief actionable title"},
                    "description": {"type": "string", "description": "What needs to be done"},
                    "activeForm": {"type": "string", "description": "Present continuous form for spinner"},
                },
                "required": ["subject"]
            }
        }

    async def call(self, subject: str, description: str = "", active_form: str = "", **kwargs: Any) -> dict:
        from claude_code.services.task_manager import get_task_manager
        tm = get_task_manager()
        task = tm.create_task(subject=subject, description=description, active_form=active_form)
        return {"task_id": task["id"], "subject": task["subject"], "status": "pending"}
