"""TaskList tool. Ported from TaskListTool."""
from __future__ import annotations
from typing import Any

TASK_LIST_TOOL_NAME = "TaskList"
DESCRIPTION = "List all tasks in the current task list"


class TaskListTool:
    name = TASK_LIST_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {"type": "object", "properties": {}, "required": []}
        }

    async def call(self, **kwargs: Any) -> dict:
        from claude_code.services.task_manager import get_task_manager
        tm = get_task_manager()
        tasks = tm.list_tasks()
        completed_ids = {t["id"] for t in tasks if t.get("status") == "completed"}
        result = [{
            "id": t["id"],
            "subject": t.get("subject", ""),
            "status": t.get("status", "pending"),
            "owner": t.get("owner"),
            "blockedBy": [b for b in t.get("blocked_by", []) if b not in completed_ids],
        } for t in tasks if not t.get("metadata", {}).get("_internal")]
        return {"tasks": result}
