"""Command descriptor for /skills. Ported from commands/skills/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "skills"
DESCRIPTION = "List available skills"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class SkillsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /skills command."""
        return {"type": "text", "value": f"/skills not yet implemented"}


default = SkillsCommand()
