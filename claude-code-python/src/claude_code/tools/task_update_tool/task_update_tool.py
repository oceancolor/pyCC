"""TaskUpdate tool. Ported from TaskUpdateTool/TaskUpdateTool.ts."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

TASK_UPDATE_TOOL_NAME = "TaskUpdate"
DESCRIPTION = "Update a task in the task list"
PROMPT = """Use this tool to update a task in the task list.

Status values: ``pending`` → ``in_progress`` → ``completed``
Use ``deleted`` to permanently remove a task.

You can update multiple fields in a single call (subject, description, status, owner, etc.).
To add dependency edges use ``addBlocks`` / ``addBlockedBy``."""

# Valid task status values (mirrors TaskStatusSchema in TS)
_VALID_STATUSES = frozenset({"pending", "in_progress", "completed", "deleted"})


class TaskUpdateTool:
    """Update metadata, status, and dependency edges on an existing task.

    Mirrors the TS ``TaskUpdateTool.call`` which:
    - Validates the task exists
    - Applies field updates via ``updateTask``
    - Handles the special ``deleted`` status via ``deleteTask``
    - Adds blocks/blockedBy edges via ``blockTask``
    """

    name = TASK_UPDATE_TOOL_NAME
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
                    "taskId": {
                        "type": "string",
                        "description": "The ID of the task to update",
                    },
                    "subject": {
                        "type": "string",
                        "description": "New subject for the task",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description for the task",
                    },
                    "activeForm": {
                        "type": "string",
                        "description": (
                            "Present continuous form shown in spinner when "
                            "in_progress (e.g., 'Running tests')"
                        ),
                    },
                    "status": {
                        "type": "string",
                        "enum": list(_VALID_STATUSES),
                        "description": "New status for the task",
                    },
                    "owner": {
                        "type": "string",
                        "description": "New owner for the task",
                    },
                    "addBlocks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Task IDs that this task blocks",
                    },
                    "addBlockedBy": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Task IDs that block this task",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Metadata keys to merge. Set a key to null to delete it.",
                        "additionalProperties": True,
                    },
                },
                "required": ["taskId"],
            },
        }

    async def call(  # noqa: PLR0912, PLR0913
        self,
        taskId: str,  # noqa: N803
        subject: Optional[str] = None,
        description: Optional[str] = None,
        activeForm: Optional[str] = None,  # noqa: N803
        status: Optional[str] = None,
        owner: Optional[str] = None,
        addBlocks: Optional[List[str]] = None,  # noqa: N803
        addBlockedBy: Optional[List[str]] = None,  # noqa: N803
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> dict:
        from claude_code.services.task_manager import get_task_manager

        tm = get_task_manager()
        existing = tm.get_task(taskId)
        if not existing:
            return {
                "success": False,
                "taskId": taskId,
                "updatedFields": [],
                "error": "Task not found",
            }

        updated_fields: List[str] = []

        # Handle deletion separately
        if status == "deleted":
            deleted = tm.delete_task(taskId)
            return {
                "success": deleted,
                "taskId": taskId,
                "updatedFields": ["deleted"] if deleted else [],
                "statusChange": {"from": existing.get("status", ""), "to": "deleted"} if deleted else None,
                "error": None if deleted else "Failed to delete task",
            }

        # Build updates dict for scalar fields
        updates: Dict[str, Any] = {}
        if subject is not None and subject != existing.get("subject"):
            updates["subject"] = subject
            updated_fields.append("subject")
        if description is not None and description != existing.get("description"):
            updates["description"] = description
            updated_fields.append("description")
        if activeForm is not None and activeForm != existing.get("active_form"):
            updates["active_form"] = activeForm
            updated_fields.append("activeForm")
        if owner is not None and owner != existing.get("owner"):
            updates["owner"] = owner
            updated_fields.append("owner")
        if metadata is not None:
            merged = dict(existing.get("metadata") or {})
            for key, val in metadata.items():
                if val is None:
                    merged.pop(key, None)
                else:
                    merged[key] = val
            updates["metadata"] = merged
            updated_fields.append("metadata")
        if status is not None and status != existing.get("status"):
            updates["status"] = status
            updated_fields.append("status")

        if updates:
            tm.update_task(taskId, updates)

        # Add dependency edges
        if addBlocks:
            for block_id in addBlocks:
                if block_id not in existing.get("blocks", []):
                    tm.block_task(taskId, block_id)
            updated_fields.append("blocks")

        if addBlockedBy:
            for blocker_id in addBlockedBy:
                if blocker_id not in existing.get("blocked_by", []):
                    tm.block_task(blocker_id, taskId)
            updated_fields.append("blockedBy")

        status_change = (
            {"from": existing.get("status", ""), "to": status}
            if status is not None and status != existing.get("status")
            else None
        )

        return {
            "success": True,
            "taskId": taskId,
            "updatedFields": updated_fields,
            "statusChange": status_change,
        }

    def map_tool_result(self, content: dict, tool_use_id: str) -> dict:
        if not content.get("success"):
            text = content.get("error") or f"Task #{content.get('taskId')} not found"
        else:
            fields = ", ".join(content.get("updatedFields", []))
            text = f"Updated task #{content.get('taskId')} {fields}"

        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": text,
        }
