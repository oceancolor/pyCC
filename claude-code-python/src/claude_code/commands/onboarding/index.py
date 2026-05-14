"""Command descriptor for /onboarding. Ported from commands/onboarding/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "onboarding"
DESCRIPTION = "Restart the onboarding flow (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class OnboardingCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /onboarding command."""
        return {"type": "local-command", "name": "onboarding", "args": args}


default = OnboardingCommand()
