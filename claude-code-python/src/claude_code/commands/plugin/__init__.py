"""Plugin command package stub."""
from __future__ import annotations
from typing import Literal
from dataclasses import dataclass

NAME = "plugin"
DESCRIPTION = "Manage plugins"
TYPE: Literal["local-jsx"] = "local-jsx"


@dataclass
class PluginCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        return {"type": "local-command", "name": "plugin", "args": args}


default = PluginCommand()
