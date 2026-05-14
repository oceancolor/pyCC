"""Command descriptor for /rewind. Ported from commands/rewind/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "rewind"
DESCRIPTION = "Restore the code and/or conversation to a previous point"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = ['checkpoint']
IS_HIDDEN: bool = False
SUPPORTS_NON_INTERACTIVE: bool = False


@dataclass
class RewindCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    aliases: List[str] = field(default_factory=lambda: ['checkpoint'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /rewind command."""
        return {"type": "text", "value": f"/rewind not yet implemented"}


default = RewindCommand()
