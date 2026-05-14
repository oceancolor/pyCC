"""Command descriptor for /bughunter. Ported from commands/bughunter/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "bughunter"
DESCRIPTION = "Start a bug hunting session (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class BughunterCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /bughunter command."""
        return {"type": "local-command", "name": "bughunter", "args": args}


default = BughunterCommand()
