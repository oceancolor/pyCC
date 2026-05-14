"""Command descriptor for /break-cache. Ported from commands/break_cache/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "break-cache"
DESCRIPTION = "Break the prompt cache (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class BreakCacheCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /break-cache command."""
        return {"type": "local-command", "name": "break-cache", "args": args}


default = BreakCacheCommand()
