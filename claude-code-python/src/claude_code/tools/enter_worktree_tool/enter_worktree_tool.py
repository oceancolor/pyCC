"""EnterWorktree tool stub. Ported from EnterWorktreeTool."""
from __future__ import annotations
from typing import Any

ENTER_WORKTREE_TOOL_NAME = "EnterWorktree"
DESCRIPTION = "Switch to a git worktree for isolated development"


class EnterWorktreeTool:
    name = ENTER_WORKTREE_TOOL_NAME
    description = DESCRIPTION

    async def call(self, path: str = "", **kwargs: Any) -> dict:
        return {"error": "Worktree switching not available in this environment"}
