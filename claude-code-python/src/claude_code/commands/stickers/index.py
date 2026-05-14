"""Command descriptor for /stickers. Ported from commands/stickers/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "stickers"
DESCRIPTION = "Toggle sticker animations"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class StickersCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /stickers command.

        Show fun stickers (ASCII art).
        """
        return {"type": "local-command", "name": "stickers", "args": args}


default = StickersCommand()
