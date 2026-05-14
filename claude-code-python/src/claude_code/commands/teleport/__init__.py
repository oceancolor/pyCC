"""teleport command package stub (ANT-internal)."""
from __future__ import annotations
from typing import Literal
from dataclasses import dataclass

NAME = "teleport"
DESCRIPTION = "Teleport to a remote session (ANT-only)"
TYPE: Literal["local-jsx"] = "local-jsx"


@dataclass
class TeleportCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        return {"type": "text", "value": "/teleport not yet implemented"}


default = TeleportCommand()
