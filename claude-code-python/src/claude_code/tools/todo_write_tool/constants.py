"""TodoWriteTool constants.

Ported from: tools/TodoWriteTool/constants.ts

Defines the canonical API-level tool name used to identify the
TodoWrite tool in tool-use messages and permission rules.

TodoWrite manages a structured in-session to-do list that allows the
agent to track a multi-step plan.  The list is stored in the session
context and shown to the user as a progress indicator.  Items can be
added, updated, or marked complete in a single call.

See also
--------
``claude_code.tools.todo_write_tool.todo_write_tool`` : Implementation.
"""
from __future__ import annotations

#: The API-level tool name used to identify the TodoWrite tool.
TODO_WRITE_TOOL_NAME: str = "TodoWrite"

__all__ = ["TODO_WRITE_TOOL_NAME"]
