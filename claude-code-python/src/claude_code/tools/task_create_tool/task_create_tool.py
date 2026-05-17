"""Task create tool. Ported from TaskCreateTool/TaskCreateTool.ts."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

TASK_CREATE_TOOL_NAME = "TaskCreate"
DESCRIPTION = "Create a new task in the task list"


class TaskCreateTool:
    """Create a new task entry in the shared task list.

    Maps to the TS ``TaskCreateTool`` which calls ``createTask(getTaskListId(), …)``.
    In the Python port the task manager is injected lazily via ``get_task_manager()``.
    """

    name = TASK_CREATE_TOOL_NAME
    description = DESCRIPTION
    should_defer = True
    is_concurrency_safe = True

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "A brief title for the task",
                    },
                    "description": {
                        "type": "string",
                        "description": "What needs to be done",
                    },
                    "activeForm": {
                        "type": "string",
                        "description": (
                            "Present continuous form shown in spinner when "
                            "in_progress (e.g., 'Running tests')"
                        ),
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Arbitrary metadata to attach to the task",
                        "additionalProperties": True,
                    },
                },
                "required": ["subject"],
            },
        }

    async def call(
        self,
        subject: str,
        description: str = "",
        active_form: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> dict:
        from claude_code.services.task_manager import get_task_manager

        tm = get_task_manager()
        task = tm.create_task(
            subject=subject,
            description=description,
            active_form=active_form,
            metadata=metadata or {},
        )
        return {
            "task": {
                "id": task["id"],
                "subject": task["subject"],
            }
        }

    def map_tool_result(self, content: dict, tool_use_id: str) -> dict:
        task = content.get("task", {})
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": f"Task #{task.get('id')} created successfully: {task.get('subject')}",
        }
