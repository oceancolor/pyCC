"""Command descriptor for /good-claude. Ported from commands/good_claude/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "good-claude"
DESCRIPTION = "Send positive feedback to improve Claude (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class GoodClaudeCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /good-claude command."""
        return {"type": "local-command", "name": "good-claude", "args": args}


default = GoodClaudeCommand()
