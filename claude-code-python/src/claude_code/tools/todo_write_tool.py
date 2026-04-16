"""
TodoWrite tool implementation
原始 TS: src/tools/TodoWriteTool/TodoWriteTool.ts

Manages session task checklist (todos).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel

from claude_code.constants.tools import TODO_WRITE_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext


# ---------------------------------------------------------------------------
# Todo item schema
# ---------------------------------------------------------------------------

class TodoItem(BaseModel):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed"] = "pending"
    priority: Literal["low", "medium", "high"] = "medium"


DESCRIPTION = """Use this tool to create and manage a task checklist for complex, multi-step tasks. This helps keep track of progress and ensures nothing is missed.

Guidelines for when to use this tool:
- When starting a complex task with 3+ steps
- When you need to track progress across multiple tool calls
- When the user asks you to keep track of tasks or create a plan

Guidelines for good todos:
- Make each todo item specific and actionable
- Update status as you complete each step
- Add new items if you discover additional required steps"""


class TodoWriteTool(Tool):
    """
    Manages the session task checklist.
    原始 TS: src/tools/TodoWriteTool/TodoWriteTool.ts
    """

    name = TODO_WRITE_TOOL_NAME
    search_hint = "manage the session task checklist"
    max_result_size_chars = 100_000

    async def description(self) -> str:
        return DESCRIPTION

    async def prompt(self) -> str:
        return DESCRIPTION

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "The updated todo list",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                            },
                        },
                        "required": ["id", "content", "status"],
                    },
                },
            },
            "required": ["todos"],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        todos = input_data.get("todos", [])

        # Store todos in context
        if context.get_app_state:
            state = context.get_app_state()
            old_todos = getattr(state, "todos", []) if state else []
        else:
            old_todos = []

        # Format for display
        status_emoji = {"pending": "⬜", "in_progress": "🔄", "completed": "✅"}
        priority_prefix = {"high": "🔴 ", "medium": "🟡 ", "low": "🟢 "}

        lines = []
        for todo in todos:
            status = todo.get("status", "pending")
            priority = todo.get("priority", "medium")
            emoji = status_emoji.get(status, "⬜")
            prefix = priority_prefix.get(priority, "")
            lines.append(f"{emoji} {prefix}{todo.get('content', '')}")

        return {
            "type": "text",
            "text": "\n".join(lines) if lines else "(empty todo list)",
            "data": {"old_todos": old_todos, "new_todos": todos},
        }

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        return ""
