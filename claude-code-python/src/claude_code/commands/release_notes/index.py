"""Command descriptor for /release-notes. Ported from commands/release_notes/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "release-notes"
DESCRIPTION = "View release notes"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
SUPPORTS_NON_INTERACTIVE: bool = True


@dataclass
class ReleaseNotesCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /release-notes command."""
        return {"type": "text", "value": f"/release-notes not yet implemented"}


default = ReleaseNotesCommand()
