# 原始 TS: tools/TaskCreateTool/TaskCreateTool.ts, tools/TaskGetTool, tools/TaskListTool, etc.
"""
TaskTool — 任务管理工具（创建/读取/列表/更新/停止）stub。

对应源码中的多个 Task*Tool，合并为一个 Python 模块，提供统一接口。
"""

from __future__ import annotations

from typing import Any, Literal

from ..tool import Tool as ToolBase, ToolUseContext
ToolResult = dict  # compat alias


class TaskCreateTool(ToolBase):
    """Create a new task/agent subtask."""

    name: str = "Task"
    description: str = (
        "Launch a new agent subtask to handle a specific piece of work. "
        "The task runs asynchronously and returns a task ID that can be "
        "used to check status or retrieve results."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
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

    def run(self, description: str, prompt: str, **kwargs: Any) -> ToolResult:
        """Create and launch a subtask."""
        # TODO: integrate with actual agent spawning / task queue
        task_id = self._create_task(description, prompt)
        return ToolResult(
            content=[
                {
                    "type": "text",
                    "text": f"Task created with ID: {task_id}\nDescription: {description}",
                }
            ]
        )

    def _create_task(self, description: str, prompt: str) -> str:
        """Create the task and return its ID."""
        # TODO: implement actual task creation
        import uuid
        return str(uuid.uuid4())


class TaskGetTool(ToolBase):
    """Get the status and output of a task."""

    name: str = "TaskGet"
    description: str = "Retrieve the current status and output of a running or completed task."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID returned by Task tool.",
                },
            },
            "required": ["task_id"],
        }

    def run(self, task_id: str, **kwargs: Any) -> ToolResult:
        # TODO: look up task by ID in task store
        return ToolResult(
            content=[
                {
                    "type": "text",
                    "text": f"Task {task_id}: status=pending (stub — not yet implemented)",
                }
            ]
        )


class TaskListTool(ToolBase):
    """List all active tasks in the current session."""

    name: str = "TaskList"
    description: str = "List all active tasks and their statuses in the current session."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def run(self, **kwargs: Any) -> ToolResult:
        # TODO: retrieve from task store
        return ToolResult(
            content=[{"type": "text", "text": "No active tasks. (stub)"}]
        )


class TaskStopTool(ToolBase):
    """Stop a running task."""

    name: str = "TaskStop"
    description: str = "Stop a running task by its ID."

    @property
    def input_schema(self) -> dict[str, Any]:
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

    def run(self, task_id: str, **kwargs: Any) -> ToolResult:
        # TODO: send stop signal to task
        return ToolResult(
            content=[{"type": "text", "text": f"Task {task_id} stop requested. (stub)"}]
        )


class TaskUpdateTool(ToolBase):
    """Send an update or message to a running task."""

    name: str = "TaskUpdate"
    description: str = "Send a message or update to a running task."

    @property
    def input_schema(self) -> dict[str, Any]:
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

    def run(self, task_id: str, message: str, **kwargs: Any) -> ToolResult:
        # TODO: route message to running task
        return ToolResult(
            content=[
                {
                    "type": "text",
                    "text": f"Update sent to task {task_id}: {message!r} (stub)",
                }
            ]
        )
