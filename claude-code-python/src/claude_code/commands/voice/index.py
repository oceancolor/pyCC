"""Command descriptor for /voice. Ported from commands/voice/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "voice"
DESCRIPTION = "Toggle voice mode"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
SUPPORTS_NON_INTERACTIVE: bool = False
AVAILABILITY: List[str] = ['claude-ai']


@dataclass
class VoiceCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    availability: List[str] = field(default_factory=lambda: ['claude-ai'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /voice command."""
        return {"type": "text", "value": f"/voice not yet implemented"}


default = VoiceCommand()
