"""TodoWriteTool. Ported from TodoWriteTool/TodoWriteTool.ts"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

TODO_WRITE_TOOL_NAME = "TodoWrite"

# In-process todo state keyed by session/agent id
_todos: Dict[str, List[Dict[str, Any]]] = {}


def get_todos(key: str) -> List[Dict[str, Any]]:
    return _todos.get(key, [])


def set_todos(key: str, todos: List[Dict[str, Any]]) -> None:
    _todos[key] = todos


class TodoWriteTool:
    """Manage the session task checklist. Ported from TodoWriteTool.ts."""

    name = TODO_WRITE_TOOL_NAME
    search_hint = "manage the session task checklist"
    max_result_size_chars = 100_000
    should_defer = True
    is_read_only = False
    strict = True

    async def description(self) -> str:
        return "Write/update the agent's task checklist (todo list)."

    async def call(
        self,
        todos: List[Dict[str, Any]],
        context: Any = None,
    ) -> Dict[str, Any]:
        """Update todos; if all completed, clear the list."""
        agent_id: Optional[str] = getattr(context, "agent_id", None) if context else None
        session_id: str = (
            agent_id
            or (getattr(context, "get_session_id", lambda: "default")() if context else "default")
        )
        old_todos = get_todos(session_id)
        all_done = all(t.get("status") == "completed" for t in todos)
        new_todos: List[Dict[str, Any]] = [] if all_done else todos

        set_todos(session_id, new_todos)

        return {
            "old_todos": old_todos,
            "new_todos": todos,
            "verification_nudge_needed": False,
        }

    def map_tool_result(self, result: Dict[str, Any], tool_use_id: str) -> Dict[str, Any]:
        nudge = result.get("verification_nudge_needed", False)
        base = (
            "Todos have been modified successfully. Ensure that you continue to use "
            "the todo list to track your progress. Please proceed with the current tasks if applicable"
        )
        text = base + (
            "\n\nNOTE: You just closed out 3+ tasks and none of them was a verification step."
            if nudge else ""
        )
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": text,
        }
