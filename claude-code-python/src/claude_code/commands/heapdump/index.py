"""Command descriptor for /heapdump. Ported from commands/heapdump/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "heapdump"
DESCRIPTION = "Dump the JS heap to ~/Desktop"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True
SUPPORTS_NON_INTERACTIVE: bool = True


@dataclass
class HeapdumpCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = IS_HIDDEN

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /heapdump command.

        Generate a heap dump for diagnostics.
        """
        return {"type": "local-command", "name": "heapdump", "args": args}


default = HeapdumpCommand()
