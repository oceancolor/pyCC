"""Command descriptor for /btw. Ported from commands/btw/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "btw"
DESCRIPTION = "Ask a quick side question without interrupting the main conversation"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "<question>"
IMMEDIATE: bool = True


@dataclass
class BtwCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    immediate: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /btw command."""
        return {"type": "text", "value": f"/btw not yet implemented"}


default = BtwCommand()
