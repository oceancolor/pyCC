"""Task stop tool. Ported from TaskStopTool/TaskStopTool.ts."""
from __future__ import annotations

from typing import Any, Optional

TASK_STOP_TOOL_NAME = "TaskStop"
DESCRIPTION = "Stop a running background task by ID"
# Backward-compatible alias (TS: aliases: ['KillShell'])
TASK_STOP_TOOL_ALIASES = ["KillShell"]


class TaskStopTool:
    """Stop a running background task.

    Mirrors the TS TaskStopTool which supports both ``task_id`` and the
    deprecated ``shell_id`` (KillShell backwards compatibility).
    """

    name = TASK_STOP_TOOL_NAME
    description = DESCRIPTION
    aliases = TASK_STOP_TOOL_ALIASES
    should_defer = True
    is_concurrency_safe = True

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the background task to stop",
                    },
                    "shell_id": {
                        "type": "string",
                        "description": "Deprecated: use task_id instead",
                    },
                },
                # Either task_id or shell_id must be provided
                "required": [],
            },
        }

    async def call(
        self,
        task_id: Optional[str] = None,
        shell_id: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        # Support both task_id and deprecated shell_id
        effective_id = task_id or shell_id
        if not effective_id:
            raise ValueError("Missing required parameter: task_id")

        from claude_code.services.task_manager import get_task_manager

        tm = get_task_manager()
        result = tm.stop_task(effective_id)

        if not result:
            return {
                "message": f"Task {effective_id} not found or could not be stopped",
                "task_id": effective_id,
                "task_type": "unknown",
            }

        return {
            "message": f"Successfully stopped task: {effective_id}",
            "task_id": effective_id,
            "task_type": result.get("type", "unknown") if isinstance(result, dict) else "unknown",
            "command": result.get("description", "") if isinstance(result, dict) else "",
        }

    def map_tool_result(self, content: dict, tool_use_id: str) -> dict:
        import json

        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": json.dumps(content),
        }
