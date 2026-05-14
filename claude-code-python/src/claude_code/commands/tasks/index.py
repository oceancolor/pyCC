"""Command descriptor for /tasks. Ported from commands/tasks/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "tasks"
DESCRIPTION = "List and manage background tasks"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['bashes']
IS_HIDDEN: bool = False


@dataclass
class TasksCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    aliases: List[str] = field(default_factory=lambda: ['bashes'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /tasks command."""
        return {"type": "text", "value": f"/tasks not yet implemented"}


default = TasksCommand()
