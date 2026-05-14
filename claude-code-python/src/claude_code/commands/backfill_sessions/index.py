"""Command descriptor for /backfill-sessions. Ported from commands/backfill_sessions/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "backfill-sessions"
DESCRIPTION = "Backfill session data (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class BackfillSessionsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /backfill-sessions command."""
        return {"type": "local-command", "name": "backfill-sessions", "args": args}


default = BackfillSessionsCommand()
