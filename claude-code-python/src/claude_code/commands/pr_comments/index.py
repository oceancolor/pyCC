"""Command descriptor for /pr-comments. Ported from commands/pr_comments/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "pr-comments"
DESCRIPTION = "Get comments from a GitHub pull request"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class PrCommentsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /pr-comments command.

        Show and respond to pull request comments.
        """
        return {"type": "local-command", "name": "pr-comments", "args": args}


default = PrCommentsCommand()
