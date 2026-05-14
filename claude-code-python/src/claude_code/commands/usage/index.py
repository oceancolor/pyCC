"""Command descriptor for /usage. Ported from commands/usage/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "usage"
DESCRIPTION = "Show plan usage limits"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
AVAILABILITY: List[str] = ['claude-ai']


@dataclass
class UsageCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    availability: List[str] = field(default_factory=lambda: ['claude-ai'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /usage command."""
        return {"type": "text", "value": f"/usage not yet implemented"}


default = UsageCommand()
