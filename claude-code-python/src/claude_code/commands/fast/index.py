"""Command descriptor for /fast. Ported from commands/fast/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "fast"
DESCRIPTION = "Toggle fast mode"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[on|off]"
AVAILABILITY: List[str] = ['claude-ai', 'console']


@dataclass
class FastCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    availability: List[str] = field(default_factory=lambda: ['claude-ai', 'console'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /fast command."""
        return {"type": "text", "value": f"/fast not yet implemented"}


default = FastCommand()
