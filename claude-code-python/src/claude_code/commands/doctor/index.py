"""Command descriptor for /doctor. Ported from commands/doctor/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "doctor"
DESCRIPTION = "Diagnose and verify your Claude Code installation and settings"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class DoctorCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /doctor command.

        Check Claude Code installation health.
        """
        return {"type": "local-command", "name": "doctor", "args": args}


default = DoctorCommand()
