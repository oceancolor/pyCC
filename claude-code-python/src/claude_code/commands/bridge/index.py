"""Command descriptor for /remote-control. Ported from commands/bridge/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "remote-control"
DESCRIPTION = "Connect this terminal for remote-control sessions"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['rc']
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[name]"
IMMEDIATE: bool = True


@dataclass
class BridgeCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    aliases: List[str] = field(default_factory=lambda: ['rc'])
    immediate: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /remote-control command."""
        return {"type": "text", "value": f"/remote-control not yet implemented"}


default = BridgeCommand()
