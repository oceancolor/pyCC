"""EnterWorktreeTool package.

Re-exports EnterWorktreeTool and its canonical name constant.

EnterWorktreeTool switches the agent's working context to a git worktree,
allowing parallel work on multiple branches without disturbing the primary
checkout.

Ported from: tools/EnterWorktreeTool/ (TypeScript)

Usage::

    from claude_code.tools.enter_worktree_tool import (
        EnterWorktreeTool,
        ENTER_WORKTREE_TOOL_NAME,
    )
"""
from __future__ import annotations

from claude_code.tools.enter_worktree_tool.enter_worktree_tool import EnterWorktreeTool
from claude_code.tools.enter_worktree_tool.constants import ENTER_WORKTREE_TOOL_NAME

__all__ = [
    "EnterWorktreeTool",
    "ENTER_WORKTREE_TOOL_NAME",
]
