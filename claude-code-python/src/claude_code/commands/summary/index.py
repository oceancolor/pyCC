"""Command descriptor for /summary. Ported from commands/summary/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "summary"
DESCRIPTION = "Generate a summary of the current conversation (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class SummaryCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /summary command."""
        return {"type": "local-command", "name": "summary", "args": args}


default = SummaryCommand()
