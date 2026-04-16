"""
TodoReadTool — 读取当前会话的 Todo 列表。
原始 TS: src/tools/TodoWriteTool/TodoWriteTool.ts (TodoRead 与 TodoWrite 共享状态)
注意：TS 源码中没有独立的 TodoReadTool 目录，对应的读取逻辑内嵌于 TodoWriteTool 中。
本文件实现 TodoRead 独立工具，从会话状态中读取 todo 列表。
"""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TODO_READ_TOOL_NAME = "TodoRead"

DESCRIPTION = (
    "Read the current to-do list. Returns all todos with their status, "
    "priority, and content. Use this to check what tasks remain before "
    "starting or after completing work."
)

PROMPT = """\
# TodoRead

Read the current session's todo list.

Returns an array of todo items. Each item has:
- `id` (string): unique identifier
- `content` (string): description of the task
- `status` (string): one of `pending`, `in_progress`, `completed`
- `priority` (string): one of `high`, `medium`, `low`

Use this at the start of a session to understand what work remains,
and before modifying todos to avoid overwriting concurrent changes.

Typical flow:
1. Call TodoRead to see current list
2. Do work
3. Call TodoWrite with updated list when done

If no todos are set, returns an empty array — not an error.
"""

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

TODO_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Unique identifier for the todo item"},
        "content": {"type": "string", "description": "Description of the task"},
        "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed"],
            "description": "Current status of the todo item",
        },
        "priority": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Priority level",
        },
    },
    "required": ["id", "content", "status", "priority"],
}


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class TodoReadTool(Tool):
    """Read the current todo list for this session.

    Mirrors the TodoWriteTool's read path: looks up todos by agent_id or
    session_id in the app state ``todos`` mapping.
    """

    name: str = TODO_READ_TOOL_NAME
    search_hint: str = "check the session task checklist"
    max_result_size_chars: int = 100_000

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    async def description(self) -> str:
        return DESCRIPTION

    async def prompt(self) -> str:
        return PROMPT

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
        """Return the current todo list from session/agent state."""
        todos = self._get_todos(context)
        return {"todos": todos}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_todos(self, context: ToolUseContext) -> list[dict[str, Any]]:
        """Retrieve todos from app state.

        Key lookup order:
        1. ``context.agent_id`` (sub-agent sessions)
        2. session_id from app state
        3. Fallback to empty list
        """
        if context.get_app_state is None:
            return []

        app_state: dict[str, Any] = context.get_app_state()
        todos_map: dict[str, Any] = app_state.get("todos", {})

        # Try agent_id first (sub-agent sessions)
        agent_id: Optional[str] = getattr(context, "agent_id", None)
        if agent_id and agent_id in todos_map:
            return list(todos_map[agent_id])

        # Try session_id
        session_id: Optional[str] = app_state.get("sessionId") or app_state.get("session_id")
        if session_id and session_id in todos_map:
            return list(todos_map[session_id])

        # Return all todos if no specific key
        if todos_map:
            # Return from the first available key
            first_key = next(iter(todos_map))
            return list(todos_map[first_key])

        return []

    def _format_todos(self, todos: list[dict[str, Any]]) -> str:
        """Format todos as a human-readable string (for non-JSON contexts)."""
        if not todos:
            return "No todos found."
        lines: list[str] = []
        for todo in todos:
            status = todo.get("status", "pending")
            priority = todo.get("priority", "medium")
            content = todo.get("content", "")
            todo_id = todo.get("id", "?")
            lines.append(f"[{status}] ({priority}) #{todo_id}: {content}")
        return "\n".join(lines)

    def map_tool_result_to_content(
        self,
        output: dict[str, Any],
        tool_use_id: str,
    ) -> dict[str, Any]:
        """Format the tool result for the API response."""
        todos: list[dict[str, Any]] = output.get("todos", [])
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": json.dumps(todos),
        }
