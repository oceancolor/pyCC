"""TodoWriteTool package.

Re-exports TodoWriteTool and its canonical name constant.

TodoWriteTool reads and writes the structured to-do list that the agent
maintains within a session.  It allows Claude to track multi-step plans,
mark items complete, and present progress to the user.

Ported from: tools/TodoWriteTool/ (TypeScript)

Usage::

    from claude_code.tools.todo_write_tool import TodoWriteTool, TODO_WRITE_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.todo_write_tool.todo_write_tool import TodoWriteTool
from claude_code.tools.todo_write_tool.constants import TODO_WRITE_TOOL_NAME

__all__ = [
    "TodoWriteTool",
    "TODO_WRITE_TOOL_NAME",
]
