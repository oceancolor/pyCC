"""
Task 工具集 — 创建/查询/列表/停止/更新后台任务。
原始 TS:
  - tools/TaskCreateTool/TaskCreateTool.ts
  - tools/TaskGetTool/TaskGetTool.ts
  - tools/TaskListTool/TaskListTool.ts
  - tools/TaskStopTool/TaskStopTool.ts
  - tools/TaskUpdateTool/TaskUpdateTool.ts

Python 将五个工具合并到同一文件，统一使用内存中的 TaskStore 进行状态管理。
在真实部署时可替换为持久化存储（Redis、sqlite 等）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TASK_CREATE_TOOL_NAME = "TaskCreate"
TASK_GET_TOOL_NAME = "TaskGet"
TASK_LIST_TOOL_NAME = "TaskList"
TASK_STOP_TOOL_NAME = "TaskStop"
TASK_UPDATE_TOOL_NAME = "TaskUpdate"

TaskStatus = Literal["pending", "in_progress", "completed", "stopped", "failed"]

# ---------------------------------------------------------------------------
# In-memory Task Store (session-scoped singleton)
# ---------------------------------------------------------------------------


@dataclass
class TaskRecord:
    """Internal task record stored in the task store."""

    id: str
    subject: str
    description: str
    status: str  # TaskStatus
    active_form: Optional[str] = None
    owner: Optional[str] = None
    blocks: List[str] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TaskStore:
    """Simple in-process task store keyed by task_list_id → dict[task_id, TaskRecord]."""

    _lists: Dict[str, Dict[str, TaskRecord]] = {}

    @classmethod
    def get_list(cls, list_id: str) -> Dict[str, TaskRecord]:
        return cls._lists.setdefault(list_id, {})

    @classmethod
    def create(cls, list_id: str, record: TaskRecord) -> None:
        cls.get_list(list_id)[record.id] = record

    @classmethod
    def get(cls, list_id: str, task_id: str) -> Optional[TaskRecord]:
        return cls.get_list(list_id).get(task_id)

    @classmethod
    def list_all(cls, list_id: str) -> List[TaskRecord]:
        return list(cls.get_list(list_id).values())

    @classmethod
    def update(cls, list_id: str, task_id: str, **kwargs: Any) -> bool:
        task = cls.get(list_id, task_id)
        if task is None:
            return False
        for k, v in kwargs.items():
            if hasattr(task, k):
                setattr(task, k, v)
        task.updated_at = datetime.now(timezone.utc).isoformat()
        return True

    @classmethod
    def delete(cls, list_id: str, task_id: str) -> bool:
        lst = cls.get_list(list_id)
        if task_id in lst:
            del lst[task_id]
            return True
        return False

    @classmethod
    def block(cls, list_id: str, blocker_id: str, blocked_id: str) -> None:
        """blocker_id blocks blocked_id."""
        blocker = cls.get(list_id, blocker_id)
        blocked = cls.get(list_id, blocked_id)
        if blocker and blocked_id not in blocker.blocks:
            blocker.blocks.append(blocked_id)
        if blocked and blocker_id not in blocked.blocked_by:
            blocked.blocked_by.append(blocker_id)


def _get_task_list_id(context: ToolUseContext) -> str:
    """Derive a task list ID from context (agent_id or session_id)."""
    agent_id: Optional[str] = getattr(context, "agent_id", None)
    if agent_id:
        return agent_id
    if context.get_app_state:
        app_state = context.get_app_state()
        sid = app_state.get("sessionId") or app_state.get("session_id")
        if sid:
            return sid
    return "default"


def _record_to_dict(task: TaskRecord) -> Dict[str, Any]:
    return {
        "id": task.id,
        "subject": task.subject,
        "description": task.description,
        "status": task.status,
        "active_form": task.active_form,
        "owner": task.owner,
        "blocks": list(task.blocks),
        "blocked_by": list(task.blocked_by),
        "metadata": dict(task.metadata),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


# ---------------------------------------------------------------------------
# TaskCreateTool
# ---------------------------------------------------------------------------


class TaskCreateTool(Tool):
    """Create a new task in the task list.

    原始 TS: tools/TaskCreateTool/TaskCreateTool.ts
    """

    name: str = TASK_CREATE_TOOL_NAME
    search_hint: str = "create a task in the task list"
    max_result_size_chars: int = 100_000

    async def description(self) -> str:
        return "Create a new task in the task list"

    async def prompt(self) -> str:
        return """\
Use this tool to create a structured task list for your current coding session.
This helps you track progress, organize complex tasks, and demonstrate
thoroughness to the user.

## When to Use This Tool

- Complex multi-step tasks (3+ distinct steps)
- Plan mode tracking
- User explicitly requests a todo list
- User provides multiple tasks

## When NOT to Use This Tool

- Single, trivial tasks that don't benefit from tracking

## Task Fields

- **subject**: Brief, actionable title (e.g., "Fix authentication bug")
- **description**: Detailed description of what needs to be done
- **active_form** (optional): Spinner text when in_progress (e.g., "Fixing authentication bug")
- **metadata** (optional): Arbitrary key-value metadata

All tasks are created with status `pending`.

## Tips

- Create tasks with clear, specific subjects that describe the outcome
- Use TaskUpdate to set up dependencies (blocks/blocked_by) after creation
- Check TaskList first to avoid creating duplicate tasks
"""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
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
                "active_form": {
                    "type": "string",
                    "description": (
                        "Present continuous form shown in spinner when in_progress "
                        '(e.g., "Running tests")'
                    ),
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Arbitrary metadata to attach to the task",
                },
            },
            "required": ["subject", "description"],
            "additionalProperties": False,
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        subject: str = input_data["subject"]
        description: str = input_data["description"]
        active_form: Optional[str] = input_data.get("active_form")
        metadata: Dict[str, Any] = input_data.get("metadata") or {}

        task_id = str(uuid.uuid4())[:8]  # short ID for readability
        list_id = _get_task_list_id(context)

        record = TaskRecord(
            id=task_id,
            subject=subject,
            description=description,
            status="pending",
            active_form=active_form,
            metadata=metadata,
        )
        TaskStore.create(list_id, record)

        return {
            "task": {
                "id": task_id,
                "subject": subject,
            }
        }

    def map_tool_result_to_content(
        self,
        output: dict[str, Any],
        tool_use_id: str,
    ) -> dict[str, Any]:
        task = output["task"]
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": f"Created task #{task['id']}: {task['subject']}",
        }


# ---------------------------------------------------------------------------
# TaskGetTool
# ---------------------------------------------------------------------------


class TaskGetTool(Tool):
    """Retrieve a task by ID from the task list.

    原始 TS: tools/TaskGetTool/TaskGetTool.ts
    """

    name: str = TASK_GET_TOOL_NAME
    search_hint: str = "retrieve a task by ID"
    max_result_size_chars: int = 100_000

    async def description(self) -> str:
        return "Get a task by ID from the task list"

    async def prompt(self) -> str:
        return """\
Use this tool to retrieve a task by its ID from the task list.

## When to Use This Tool

- When you need the full description and context before starting work on a task
- To understand task dependencies (what it blocks, what blocks it)
- After being assigned a task, to get complete requirements

## Output

Returns full task details:
- **subject**: Task title
- **description**: Detailed requirements and context
- **status**: 'pending', 'in_progress', or 'completed'
- **blocks**: Tasks waiting on this one to complete
- **blocked_by**: Tasks that must complete before this one can start

## Tips

- After fetching a task, verify its blocked_by list is empty before beginning work
- Use TaskList to see all tasks in summary form
"""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to retrieve",
                },
            },
            "required": ["task_id"],
            "additionalProperties": False,
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        task_id: str = input_data["task_id"]
        list_id = _get_task_list_id(context)
        task = TaskStore.get(list_id, task_id)

        if task is None:
            return {"task": None}

        return {"task": _record_to_dict(task)}

    def map_tool_result_to_content(
        self,
        output: dict[str, Any],
        tool_use_id: str,
    ) -> dict[str, Any]:
        task = output.get("task")
        if not task:
            return {
                "tool_use_id": tool_use_id,
                "type": "tool_result",
                "content": "Task not found",
            }
        lines = [
            f"Task #{task['id']}: {task['subject']}",
            f"Status: {task['status']}",
            f"Description: {task['description']}",
        ]
        if task.get("blocked_by"):
            ids = ", ".join(f"#{i}" for i in task["blocked_by"])
            lines.append(f"Blocked by: {ids}")
        if task.get("blocks"):
            ids = ", ".join(f"#{i}" for i in task["blocks"])
            lines.append(f"Blocks: {ids}")
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": "\n".join(lines),
        }


# ---------------------------------------------------------------------------
# TaskListTool
# ---------------------------------------------------------------------------


class TaskListTool(Tool):
    """List all tasks in the task list.

    原始 TS: tools/TaskListTool/TaskListTool.ts
    """

    name: str = TASK_LIST_TOOL_NAME
    search_hint: str = "list all tasks"
    max_result_size_chars: int = 100_000

    async def description(self) -> str:
        return "List all tasks in the task list"

    async def prompt(self) -> str:
        return """\
Use this tool to list all tasks in the task list.

## When to Use This Tool

- To see what tasks are available to work on (status: 'pending', no owner, not blocked)
- To check overall progress on the project
- To find tasks that are blocked and need dependencies resolved
- After completing a task, to check for newly unblocked work

## Output

Returns a summary of each task:
- **id**: Task identifier (use with TaskGet, TaskUpdate)
- **subject**: Task title
- **status**: Current status
- **owner**: Who is working on the task (if assigned)
- **blocked_by**: IDs of tasks that must complete first

## Tips

- Prefer working on tasks in ID order (lowest ID first) when multiple are available
- Filter for tasks with status 'pending', no owner, and empty blocked_by list to find available work
"""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        list_id = _get_task_list_id(context)
        all_tasks = TaskStore.list_all(list_id)

        # Filter out internal tasks; exclude completed blockers from blocked_by
        completed_ids = {t.id for t in all_tasks if t.status == "completed"}
        tasks = [
            {
                "id": t.id,
                "subject": t.subject,
                "status": t.status,
                "owner": t.owner,
                "blocked_by": [bid for bid in t.blocked_by if bid not in completed_ids],
            }
            for t in all_tasks
            if not t.metadata.get("_internal")
        ]

        return {"tasks": tasks}

    def map_tool_result_to_content(
        self,
        output: dict[str, Any],
        tool_use_id: str,
    ) -> dict[str, Any]:
        tasks: List[Dict[str, Any]] = output.get("tasks", [])
        if not tasks:
            return {
                "tool_use_id": tool_use_id,
                "type": "tool_result",
                "content": "No tasks found",
            }
        lines = []
        for task in tasks:
            owner_str = f" ({task['owner']})" if task.get("owner") else ""
            blocked_ids = task.get("blocked_by", [])
            blocked_str = (
                f" [blocked by {', '.join(f'#{i}' for i in blocked_ids)}]"
                if blocked_ids
                else ""
            )
            lines.append(
                f"#{task['id']} [{task['status']}] {task['subject']}{owner_str}{blocked_str}"
            )
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": "\n".join(lines),
        }


# ---------------------------------------------------------------------------
# TaskStopTool
# ---------------------------------------------------------------------------


class TaskStopTool(Tool):
    """Stop a running background task.

    原始 TS: tools/TaskStopTool/TaskStopTool.ts
    原始别名: KillShell (deprecated)
    """

    name: str = TASK_STOP_TOOL_NAME
    search_hint: str = "kill a running background task"
    max_result_size_chars: int = 100_000

    async def description(self) -> str:
        return "Stop a running background task by ID"

    async def prompt(self) -> str:
        return """\
Stop a running background task by its ID.

Use when:
- A long-running command is no longer needed
- A task is stuck and needs to be killed
- You want to cancel a background operation

The task will be transitioned to status 'stopped'.
"""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
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
            "required": [],
            "additionalProperties": False,
        }

    async def validate_input(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> Any:
        from claude_code.tool import ValidationResultFail, ValidationResultOk

        task_id: Optional[str] = input_data.get("task_id") or input_data.get("shell_id")
        if not task_id:
            return ValidationResultFail(
                result=False,
                message="Missing required parameter: task_id",
                error_code=1,
            )

        list_id = _get_task_list_id(context)
        task = TaskStore.get(list_id, task_id)
        if task is None:
            return ValidationResultFail(
                result=False,
                message=f"No task found with ID: {task_id}",
                error_code=1,
            )
        if task.status != "in_progress":
            return ValidationResultFail(
                result=False,
                message=f"Task {task_id} is not running (status: {task.status})",
                error_code=3,
            )
        return ValidationResultOk()

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        task_id: Optional[str] = input_data.get("task_id") or input_data.get("shell_id")
        if not task_id:
            raise ValueError("Missing required parameter: task_id")

        list_id = _get_task_list_id(context)
        task = TaskStore.get(list_id, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        TaskStore.update(list_id, task_id, status="stopped")

        return {
            "message": f"Successfully stopped task: {task_id} ({task.subject})",
            "task_id": task_id,
            "task_type": "task",
            "command": task.subject,
        }

    def map_tool_result_to_content(
        self,
        output: dict[str, Any],
        tool_use_id: str,
    ) -> dict[str, Any]:
        import json
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": json.dumps(output),
        }


# ---------------------------------------------------------------------------
# TaskUpdateTool
# ---------------------------------------------------------------------------


class TaskUpdateTool(Tool):
    """Update a task in the task list.

    原始 TS: tools/TaskUpdateTool/TaskUpdateTool.ts
    """

    name: str = TASK_UPDATE_TOOL_NAME
    search_hint: str = "update a task"
    max_result_size_chars: int = 100_000

    async def description(self) -> str:
        return "Update a task in the task list"

    async def prompt(self) -> str:
        return """\
Use this tool to update a task in the task list.

## When to Use This Tool

- Mark a task as in_progress BEFORE beginning work
- Mark a task as completed AFTER fully completing it
- Delete a task (set status to 'deleted') when it's no longer needed
- Update subject, description, or active_form when requirements change
- Assign an owner with `owner` field
- Set up dependencies with `add_blocks` / `add_blocked_by`
- Attach metadata with `metadata` dict (set key to null to remove)

## Status Values

- `pending`: Not yet started
- `in_progress`: Work is underway
- `completed`: Fully done (only when truly complete)
- `deleted`: Remove the task permanently

## Important

- ONLY mark completed when ALL work is done (tests pass, no blockers)
- After completing, call TaskList to find the next available task
"""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "task_id": {
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
                "active_form": {
                    "type": "string",
                    "description": (
                        'Present continuous form shown in spinner when in_progress (e.g., "Running tests")'
                    ),
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "deleted"],
                    "description": "New status for the task",
                },
                "owner": {
                    "type": "string",
                    "description": "New owner for the task",
                },
                "add_blocks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that this task blocks (cannot start until this completes)",
                },
                "add_blocked_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that block this task (must complete before this can start)",
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Metadata keys to merge into the task. Set a key to null to delete it.",
                },
            },
            "required": ["task_id"],
            "additionalProperties": False,
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        task_id: str = input_data["task_id"]
        list_id = _get_task_list_id(context)

        existing = TaskStore.get(list_id, task_id)
        if existing is None:
            return {
                "success": False,
                "task_id": task_id,
                "updated_fields": [],
                "error": "Task not found",
            }

        status: Optional[str] = input_data.get("status")

        # Handle deletion
        if status == "deleted":
            deleted = TaskStore.delete(list_id, task_id)
            return {
                "success": deleted,
                "task_id": task_id,
                "updated_fields": ["deleted"] if deleted else [],
                "error": None if deleted else "Failed to delete task",
                "status_change": {"from": existing.status, "to": "deleted"} if deleted else None,
            }

        # Apply scalar updates
        updates: Dict[str, Any] = {}
        updated_fields: List[str] = []

        for field_name in ("subject", "description", "active_form", "owner"):
            value = input_data.get(field_name)
            if value is not None and value != getattr(existing, field_name, None):
                updates[field_name] = value
                updated_fields.append(field_name)

        if status is not None and status != existing.status:
            updates["status"] = status
            updated_fields.append("status")

        # Merge metadata
        metadata_patch: Optional[Dict[str, Any]] = input_data.get("metadata")
        if metadata_patch is not None:
            merged = dict(existing.metadata)
            for k, v in metadata_patch.items():
                if v is None:
                    merged.pop(k, None)
                else:
                    merged[k] = v
            updates["metadata"] = merged
            updated_fields.append("metadata")

        if updates:
            TaskStore.update(list_id, task_id, **updates)

        # Handle dependency edges
        add_blocks: List[str] = input_data.get("add_blocks") or []
        for bid in add_blocks:
            if bid not in existing.blocks:
                TaskStore.block(list_id, task_id, bid)
        if add_blocks:
            updated_fields.append("blocks")

        add_blocked_by: List[str] = input_data.get("add_blocked_by") or []
        for blocker_id in add_blocked_by:
            if blocker_id not in existing.blocked_by:
                TaskStore.block(list_id, blocker_id, task_id)
        if add_blocked_by:
            updated_fields.append("blocked_by")

        status_change = (
            {"from": existing.status, "to": status}
            if status is not None and status != existing.status
            else None
        )

        return {
            "success": True,
            "task_id": task_id,
            "updated_fields": updated_fields,
            "status_change": status_change,
        }

    def map_tool_result_to_content(
        self,
        output: dict[str, Any],
        tool_use_id: str,
    ) -> dict[str, Any]:
        if not output.get("success"):
            error = output.get("error") or f"Task #{output['task_id']} not found"
            return {
                "tool_use_id": tool_use_id,
                "type": "tool_result",
                "content": error,
            }
        task_id = output["task_id"]
        fields_str = ", ".join(output.get("updated_fields", []))
        content = f"Updated task #{task_id}: {fields_str}"
        status_change = output.get("status_change")
        if status_change and status_change.get("to") == "completed":
            content += (
                "\n\nTask completed. Call TaskList now to find your next "
                "available task or see if your work unblocked others."
            )
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": content,
        }
