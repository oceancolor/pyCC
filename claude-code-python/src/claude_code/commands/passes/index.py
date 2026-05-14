"""Command descriptor for /passes. Ported from commands/passes/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "passes"
DESCRIPTION = "Share a free week of Claude Code with friends"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class PassesCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /passes command.

        Show multi-pass processing status.
        """
        return {"type": "local-command", "name": "passes", "args": args}


default = PassesCommand()
