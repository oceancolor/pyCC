"""Command descriptor for /mock-limits. Ported from commands/mock_limits/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "mock-limits"
DESCRIPTION = "Simulate rate limiting for testing (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class MockLimitsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /mock-limits command."""
        return {"type": "local-command", "name": "mock-limits", "args": args}


default = MockLimitsCommand()
