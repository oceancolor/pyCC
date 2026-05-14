"""Command descriptor for /upgrade. Ported from commands/upgrade/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "upgrade"
DESCRIPTION = "Upgrade to Max for higher rate limits and more Opus"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
AVAILABILITY: List[str] = ['claude-ai']


@dataclass
class UpgradeCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    availability: List[str] = field(default_factory=lambda: ['claude-ai'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /upgrade command.

        Upgrade Claude Code to the latest version.
        """
        return {"type": "local-command", "name": "upgrade", "args": args}


default = UpgradeCommand()
