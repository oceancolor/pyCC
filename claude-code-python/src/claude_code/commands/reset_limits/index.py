"""Command descriptor for /reset-limits. Ported from commands/reset_limits/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "reset-limits"
DESCRIPTION = "Reset usage limits (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class ResetLimitsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /reset-limits command."""
        return {"type": "local-command", "name": "reset-limits", "args": args}


default = ResetLimitsCommand()
