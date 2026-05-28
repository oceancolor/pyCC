# 原始 TS: tools/TaskCreateTool/TaskCreateTool.ts, tools/TaskGetTool, etc.
"""
TaskTool — 任务管理工具（创建/读取/列表/更新/停止）。

对应源码中的多个 Task*Tool，合并为一个 Python 模块。
原始 Claude Code 中 Task 工具用于启动子 Agent 任务（in-process 或独立进程）；
此 Python 实现提供完整接口，内部使用轻量内存任务存储，
可在未来替换为真正的子 Agent 调度后端。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..tool import Tool as ToolBase, ToolInputJSONSchema, ToolUseContext


# ─────────────────────────────────────────────────────────────────────────────
# In-process task store (session-scoped singleton)
# ─────────────────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class TaskRecord:
    task_id: str
    description: str
    prompt: str
    status: TaskStatus = TaskStatus.PENDING
    output: str = ""
    messages: List[str] = field(default_factory=list)
    error: Optional[str] = None


# Module-level task store (lives for the duration of the Python process)
_TASK_STORE: Dict[str, TaskRecord] = {}


def _create_task(description: str, prompt: str) -> str:
    task_id = str(uuid.uuid4())[:8]
    _TASK_STORE[task_id] = TaskRecord(
        task_id=task_id,
        description=description,
        prompt=prompt,
        status=TaskStatus.PENDING,
    )
    return task_id


def _get_task(task_id: str) -> Optional[TaskRecord]:
    return _TASK_STORE.get(task_id)


def _list_tasks() -> List[TaskRecord]:
    return list(_TASK_STORE.values())


def _stop_task(task_id: str) -> bool:
    t = _TASK_STORE.get(task_id)
    if t is None:
        return False
    if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
        t.status = TaskStatus.STOPPED
    return True


def _update_task(task_id: str, message: str) -> bool:
    t = _TASK_STORE.get(task_id)
    if t is None:
        return False
    t.messages.append(message)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# TaskCreateTool
# ─────────────────────────────────────────────────────────────────────────────

class TaskCreateTool(ToolBase):
    """Launch a new agent subtask."""

    name = "Task"
    search_hint = "create task subtask agent spawn"

    async def description(self) -> str:
        return (
            "Launch a new agent subtask to handle a specific piece of work. "
            "The task runs asynchronously and returns a task ID that can be used "
            "to check status or retrieve results."
        )

    async def prompt(self) -> str:
        return """\
Launch a new agent subtask to work on a specific sub-problem in parallel.

Usage:
- Provide a clear description and a detailed prompt for the subtask.
- Returns a task_id that you can use with TaskGet, TaskList, TaskUpdate, or TaskStop.
- Use this when you want to delegate work to a sub-agent and continue other work.
- Do NOT use this for simple file reads or bash commands — use the dedicated tools instead.
- Each task runs in isolation with its own context."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "A clear description of what the task should accomplish.",
                },
                "prompt": {
                    "type": "string",
                    "description": "The full prompt/instructions for the subtask agent.",
                },
            },
            "required": ["description", "prompt"],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        description: str = input_data["description"]
        prompt: str = input_data["prompt"]

        if not description.strip():
            return {"type": "text", "text": "Error: description is required.", "is_error": True}
        if not prompt.strip():
            return {"type": "text", "text": "Error: prompt is required.", "is_error": True}

        task_id = _create_task(description, prompt)
        return {
            "type": "text",
            "text": f"Task created.\ntask_id: {task_id}\nDescription: {description}\nStatus: pending",
        }


# ─────────────────────────────────────────────────────────────────────────────
# TaskGetTool
# ─────────────────────────────────────────────────────────────────────────────

class TaskGetTool(ToolBase):
    """Get the status and output of a task."""

    name = "TaskGet"
    search_hint = "get task status output result"
    is_read_only = True

    async def description(self) -> str:
        return "Retrieve the current status and output of a running or completed task."

    async def prompt(self) -> str:
        return """\
Retrieve the current status and output of a task by its ID.

Usage:
- Pass the task_id returned by the Task tool.
- Returns status (pending/running/completed/failed/stopped) and any output collected so far.
- Poll periodically for long-running tasks."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID returned by the Task tool.",
                },
            },
            "required": ["task_id"],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        task_id: str = input_data["task_id"]
        record = _get_task(task_id)

        if record is None:
            return {
                "type": "text",
                "text": f"Error: Task not found: {task_id}",
                "is_error": True,
            }

        lines = [
            f"task_id: {record.task_id}",
            f"status: {record.status.value}",
            f"description: {record.description}",
        ]
        if record.output:
            lines.append(f"output:\n{record.output}")
        if record.messages:
            lines.append(f"messages ({len(record.messages)}):")
            for m in record.messages[-5:]:  # last 5
                lines.append(f"  - {m}")
        if record.error:
            lines.append(f"error: {record.error}")

        return {"type": "text", "text": "\n".join(lines)}


# ─────────────────────────────────────────────────────────────────────────────
# TaskListTool
# ─────────────────────────────────────────────────────────────────────────────

class TaskListTool(ToolBase):
    """List all tasks in the current session."""

    name = "TaskList"
    search_hint = "list tasks session active"
    is_read_only = True

    async def description(self) -> str:
        return "List all tasks and their statuses in the current session."

    async def prompt(self) -> str:
        return """\
List all tasks that have been created in the current session.

Usage:
- Returns task IDs, descriptions, and statuses.
- Use TaskGet to get detailed output for a specific task."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        tasks = _list_tasks()

        if not tasks:
            return {"type": "text", "text": "No tasks in current session."}

        lines = [f"Tasks ({len(tasks)} total):"]
        for t in tasks:
            lines.append(f"  [{t.status.value:10s}] {t.task_id}  {t.description[:60]}")

        return {"type": "text", "text": "\n".join(lines)}


# ─────────────────────────────────────────────────────────────────────────────
# TaskStopTool
# ─────────────────────────────────────────────────────────────────────────────

class TaskStopTool(ToolBase):
    """Stop a running task."""

    name = "TaskStop"
    search_hint = "stop cancel task kill"

    async def description(self) -> str:
        return "Stop a running or pending task by its ID."

    async def prompt(self) -> str:
        return """\
Stop a running or pending task.

Usage:
- Pass the task_id of the task to stop.
- The task will be marked as stopped; no further execution will occur.
- Completed or already-stopped tasks cannot be re-stopped."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to stop.",
                },
            },
            "required": ["task_id"],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        task_id: str = input_data["task_id"]
        record = _get_task(task_id)

        if record is None:
            return {
                "type": "text",
                "text": f"Error: Task not found: {task_id}",
                "is_error": True,
            }

        if record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return {
                "type": "text",
                "text": f"Task {task_id} is already {record.status.value}, cannot stop.",
            }

        _stop_task(task_id)
        return {"type": "text", "text": f"Task {task_id} stopped."}


# ─────────────────────────────────────────────────────────────────────────────
# TaskUpdateTool
# ─────────────────────────────────────────────────────────────────────────────

class TaskUpdateTool(ToolBase):
    """Send a message or update to a running task."""

    name = "TaskUpdate"
    search_hint = "update send message task"

    async def description(self) -> str:
        return "Send a message or update to a running task."

    async def prompt(self) -> str:
        return """\
Send a message or additional instruction to a running task.

Usage:
- Pass the task_id and the message to deliver.
- Messages are appended to the task's message log; the sub-agent may read them.
- Useful for steering a long-running task mid-execution."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to update.",
                },
                "message": {
                    "type": "string",
                    "description": "Message or update to send to the task.",
                },
            },
            "required": ["task_id", "message"],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        task_id: str = input_data["task_id"]
        message: str = input_data["message"]

        record = _get_task(task_id)
        if record is None:
            return {
                "type": "text",
                "text": f"Error: Task not found: {task_id}",
                "is_error": True,
            }

        if record.status in (TaskStatus.COMPLETED, TaskStatus.STOPPED, TaskStatus.FAILED):
            return {
                "type": "text",
                "text": f"Task {task_id} is {record.status.value}; cannot send updates.",
                "is_error": True,
            }

        _update_task(task_id, message)
        return {
            "type": "text",
            "text": f"Update sent to task {task_id}. Total messages: {len(record.messages)}",
        }
