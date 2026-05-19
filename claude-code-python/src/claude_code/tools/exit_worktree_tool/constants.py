"""ExitWorktreeTool constants.

Ported from: tools/ExitWorktreeTool/constants.ts

Defines the canonical API-level tool name used to identify the
ExitWorktree tool in tool-use messages and permission rules.

After an agent finishes working in a git worktree (entered via
``EnterWorktreeTool``), it calls ``ExitWorktreeTool`` to return its
working context to the primary checkout directory.

See also
--------
``claude_code.tools.enter_worktree_tool.constants`` : EnterWorktree name.
``claude_code.tools.exit_worktree_tool.exit_worktree_tool`` : Implementation.
"""
from __future__ import annotations

#: The API-level tool name used to identify the ExitWorktree tool.
EXIT_WORKTREE_TOOL_NAME: str = "ExitWorktree"

__all__ = ["EXIT_WORKTREE_TOOL_NAME"]
