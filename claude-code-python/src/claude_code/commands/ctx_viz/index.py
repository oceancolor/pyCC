"""Command descriptor for /ctx-viz. Ported from commands/ctx_viz/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "ctx-viz"
DESCRIPTION = "Visualize context usage in detail (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class CtxVizCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /ctx-viz command."""
        return {"type": "local-command", "name": "ctx-viz", "args": args}


default = CtxVizCommand()
