"""Command descriptor for /feedback. Ported from commands/feedback/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "feedback"
DESCRIPTION = "Submit feedback about Claude Code"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['bug']
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[report]"


@dataclass
class FeedbackCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    aliases: List[str] = field(default_factory=lambda: ['bug'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /feedback command."""
        return {"type": "text", "value": f"/feedback not yet implemented"}


default = FeedbackCommand()
