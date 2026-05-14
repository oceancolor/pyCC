"""Command descriptor for /config. Ported from commands/config/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "config"
DESCRIPTION = "Open config panel"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['settings']
IS_HIDDEN: bool = False


@dataclass
class ConfigCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    aliases: List[str] = field(default_factory=lambda: ['settings'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /config command."""
        return {"type": "text", "value": f"/config not yet implemented"}


default = ConfigCommand()
