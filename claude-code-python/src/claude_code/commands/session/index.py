"""Command descriptor for /session. Ported from commands/session/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "session"
DESCRIPTION = "Show remote session URL and QR code"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['remote']
IS_HIDDEN: bool = False


@dataclass
class SessionCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    aliases: List[str] = field(default_factory=lambda: ['remote'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /session command."""
        return {"type": "text", "value": f"/session not yet implemented"}


default = SessionCommand()
