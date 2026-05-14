"""Command descriptor for /chrome. Ported from commands/chrome/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "chrome"
DESCRIPTION = "Claude in Chrome (Beta) settings"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
AVAILABILITY: List[str] = ['claude-ai']


@dataclass
class ChromeCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    availability: List[str] = field(default_factory=lambda: ['claude-ai'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /chrome command.

        Launch Claude in Chrome extension mode.
        """
        return {"type": "local-command", "name": "chrome", "args": args}


default = ChromeCommand()
