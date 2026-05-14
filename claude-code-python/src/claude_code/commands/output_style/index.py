"""Command descriptor for /output-style. Ported from commands/output_style/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "output-style"
DESCRIPTION = "Deprecated: use /config to change output style"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = True


@dataclass
class OutputStyleCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = IS_HIDDEN

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /output-style command."""
        return {"type": "text", "value": f"/output-style not yet implemented"}


default = OutputStyleCommand()
