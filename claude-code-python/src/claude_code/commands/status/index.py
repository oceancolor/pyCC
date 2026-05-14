"""Command descriptor for /status. Ported from commands/status/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "status"
DESCRIPTION = "Show Claude Code status including version, model, account, API connectivity, and tool statuses"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
IMMEDIATE: bool = True


@dataclass
class StatusCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    immediate: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /status command.

        Show current project status.
        """
        return {"type": "local-command", "name": "status", "args": args}


default = StatusCommand()
