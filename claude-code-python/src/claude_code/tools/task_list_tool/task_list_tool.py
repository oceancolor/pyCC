"""TaskList tool. Ported from TaskListTool/TaskListTool.ts."""
from __future__ import annotations

from typing import Any, Dict, List, Set

TASK_LIST_TOOL_NAME = "TaskList"
DESCRIPTION = "List all tasks in the current task list"


class TaskListTool:
    """Return all non-internal tasks, filtering resolved blockers.

    Mirrors the TS ``TaskListTool.call`` which:
    1. Fetches all tasks with ``listTasks(taskListId)``
    2. Filters out tasks where ``metadata._internal`` is truthy
    3. Strips already-completed task IDs from each task's ``blockedBy`` list
    """

    name = TASK_LIST_TOOL_NAME
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
                "properties": {},
                "required": [],
            },
        }

    async def call(self, **kwargs: Any) -> dict:
        from claude_code.services.task_manager import get_task_manager

        tm = get_task_manager()
        all_tasks: List[Dict[str, Any]] = tm.list_tasks()

        # Filter internal tasks
        visible = [t for t in all_tasks if not t.get("metadata", {}).get("_internal")]

        # Build resolved set (completed task IDs) for blocker filtering
        resolved: Set[str] = {t["id"] for t in visible if t.get("status") == "completed"}

        tasks = [
            {
                "id": t["id"],
                "subject": t.get("subject", ""),
                "status": t.get("status", "pending"),
                "owner": t.get("owner"),
                "blockedBy": [b for b in t.get("blocked_by", []) if b not in resolved],
            }
            for t in visible
        ]

        return {"tasks": tasks}

    def map_tool_result(self, content: dict, tool_use_id: str) -> dict:
        tasks: List[dict] = content.get("tasks", [])
        if not tasks:
            text = "No tasks found"
        else:
            lines = []
            for task in tasks:
                owner = f" ({task['owner']})" if task.get("owner") else ""
                blocked_by: List[str] = task.get("blockedBy", [])
                blocked = (
                    " [blocked by " + ", ".join(f"#{i}" for i in blocked_by) + "]"
                    if blocked_by
                    else ""
                )
                lines.append(
                    f"#{task['id']} [{task['status']}] {task['subject']}{owner}{blocked}"
                )
            text = "\n".join(lines)

        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": text,
        }
