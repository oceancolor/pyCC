"""Command descriptor for /teleport. Ported from commands/teleport/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "teleport"
DESCRIPTION = "Teleport to a remote session (ANT-only)"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class TeleportCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /teleport command."""
        return {"type": "local-command", "name": "teleport", "args": args}


default = TeleportCommand()
