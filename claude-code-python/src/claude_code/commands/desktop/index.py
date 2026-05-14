"""Command descriptor for /desktop. Ported from commands/desktop/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "desktop"
DESCRIPTION = "Continue the current session in Claude Desktop"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['app']
IS_HIDDEN: bool = False
AVAILABILITY: List[str] = ['claude-ai']


@dataclass
class DesktopCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    aliases: List[str] = field(default_factory=lambda: ['app'])
    availability: List[str] = field(default_factory=lambda: ['claude-ai'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /desktop command."""
        return {"type": "text", "value": f"/desktop not yet implemented"}


default = DesktopCommand()
