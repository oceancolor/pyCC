"""Command descriptor for /mobile. Ported from commands/mobile/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "mobile"
DESCRIPTION = "Show QR code to download the Claude mobile app"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['ios', 'android']
IS_HIDDEN: bool = False


@dataclass
class MobileCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    aliases: List[str] = field(default_factory=lambda: ['ios', 'android'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /mobile command."""
        return {"type": "text", "value": f"/mobile not yet implemented"}


default = MobileCommand()
