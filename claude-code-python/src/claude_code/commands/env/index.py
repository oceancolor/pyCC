"""Command descriptor for /env. Ported from commands/env/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "env"
DESCRIPTION = "Show environment variables (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class EnvCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /env command."""
        return {"type": "local-command", "name": "env", "args": args}


default = EnvCommand()
