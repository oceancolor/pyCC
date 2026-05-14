"""Command descriptor for /thinkback-play. Ported from commands/thinkback_play/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "thinkback-play"
DESCRIPTION = "Play the thinkback animation"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True
SUPPORTS_NON_INTERACTIVE: bool = False


@dataclass
class ThinkbackPlayCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_hidden: bool = IS_HIDDEN

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /thinkback-play command."""
        return {"type": "text", "value": f"/thinkback-play not yet implemented"}


default = ThinkbackPlayCommand()
