"""Command descriptor for /ant-trace. Ported from commands/ant_trace/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "ant-trace"
DESCRIPTION = "Trace ANT-internal events (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class AntTraceCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /ant-trace command."""
        return {"type": "local-command", "name": "ant-trace", "args": args}


default = AntTraceCommand()
