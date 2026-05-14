"""Command descriptor for /context. Ported from commands/context/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "context"
DESCRIPTION = "Visualize current context usage as a colored grid"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class ContextCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /context command."""
        return {"type": "text", "value": f"/context not yet implemented"}


default = ContextCommand()
