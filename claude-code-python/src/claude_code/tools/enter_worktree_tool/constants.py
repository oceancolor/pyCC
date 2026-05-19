"""EnterWorktreeTool constants.

Ported from: tools/EnterWorktreeTool/constants.ts

Defines the canonical API-level tool name used to identify the
EnterWorktree tool in tool-use messages and permission rules.

Git worktrees allow multiple checked-out branches to coexist on disk
simultaneously.  The ``EnterWorktree`` tool switches the agent's working
context to one of these checked-out worktrees, enabling parallel work on
different branches without stashing or switching the primary checkout.

See also
--------
``claude_code.tools.exit_worktree_tool.constants`` : ExitWorktree name.
``claude_code.tools.enter_worktree_tool.enter_worktree_tool`` : Implementation.
"""
from __future__ import annotations

#: The API-level tool name used to identify the EnterWorktree tool.
ENTER_WORKTREE_TOOL_NAME: str = "EnterWorktree"

__all__ = ["ENTER_WORKTREE_TOOL_NAME"]
