"""Command descriptor for /tag. Ported from commands/tag/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "tag"
DESCRIPTION = "Toggle a searchable tag on the current session"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "<tag-name>"


@dataclass
class TagCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /tag command.

        Add or view tags for the current session.
        """
        return {"type": "local-command", "name": "tag", "args": args}


default = TagCommand()
