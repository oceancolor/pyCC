"""Command descriptor for /debug-tool-call. Ported from commands/debug_tool_call/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "debug-tool-call"
DESCRIPTION = "Debug a tool call (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class DebugToolCallCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /debug-tool-call command."""
        return {"type": "local-command", "name": "debug-tool-call", "args": args}


default = DebugToolCallCommand()
