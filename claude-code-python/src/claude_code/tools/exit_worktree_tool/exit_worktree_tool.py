"""ExitWorktree tool stub. Ported from ExitWorktreeTool."""
from __future__ import annotations

EXIT_WORKTREE_TOOL_NAME = "ExitWorktree"
DESCRIPTION = "Exit the current git worktree and return to the main worktree"


class ExitWorktreeTool:
    name = EXIT_WORKTREE_TOOL_NAME
    description = DESCRIPTION

    async def call(self, **kwargs) -> dict:
        return {"error": "Worktree switching not available in this environment"}
