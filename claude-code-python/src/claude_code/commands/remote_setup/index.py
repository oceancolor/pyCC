"""Command descriptor for /web-setup. Ported from commands/remote_setup/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "web-setup"
DESCRIPTION = "Setup Claude Code on the web"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
AVAILABILITY: List[str] = ['claude-ai']


@dataclass
class RemoteSetupCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    availability: List[str] = field(default_factory=lambda: ['claude-ai'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /web-setup command."""
        return {"type": "text", "value": f"/web-setup not yet implemented"}


default = RemoteSetupCommand()
