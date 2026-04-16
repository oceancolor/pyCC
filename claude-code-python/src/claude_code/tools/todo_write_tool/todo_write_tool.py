"""TodoWriteTool. Ported from TodoWriteTool/TodoWriteTool.ts"""
from __future__ import annotations
from typing import Any, List

TODO_WRITE_TOOL_NAME = "TodoWrite"

_session_todos: List[dict] = []


class TodoWriteTool:
    name = TODO_WRITE_TOOL_NAME
    description = "Write/update the session task checklist."
    is_read_only = False

    async def call(self, todos: List[dict], context: Any = None) -> dict:
        global _session_todos
        old_todos = list(_session_todos)
        _session_todos = [dict(t) for t in todos]
        return {"type": "success", "old_todos": old_todos, "new_todos": list(_session_todos)}
