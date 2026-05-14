"""Command descriptor for /sandbox. Ported from commands/sandbox_toggle/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "sandbox"
DESCRIPTION = "Toggle sandbox mode"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class SandboxToggleCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /sandbox command."""
        return {"type": "text", "value": f"/sandbox not yet implemented"}


default = SandboxToggleCommand()
