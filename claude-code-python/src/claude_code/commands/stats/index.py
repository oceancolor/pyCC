"""Command descriptor for /stats. Ported from commands/stats/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "stats"
DESCRIPTION = "Show your Claude Code usage statistics and activity"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class StatsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /stats command."""
        return {"type": "text", "value": f"/stats not yet implemented"}


default = StatsCommand()
