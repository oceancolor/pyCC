"""ExitWorktreeTool package.

Re-exports ExitWorktreeTool and its canonical name constant.

ExitWorktreeTool exits the current git worktree context, returning the
agent's working directory back to the primary checkout.

Ported from: tools/ExitWorktreeTool/ (TypeScript)

Usage::

    from claude_code.tools.exit_worktree_tool import (
        ExitWorktreeTool,
        EXIT_WORKTREE_TOOL_NAME,
    )
"""
from __future__ import annotations

from claude_code.tools.exit_worktree_tool.exit_worktree_tool import ExitWorktreeTool
from claude_code.tools.exit_worktree_tool.constants import EXIT_WORKTREE_TOOL_NAME

__all__ = [
    "ExitWorktreeTool",
    "EXIT_WORKTREE_TOOL_NAME",
]
