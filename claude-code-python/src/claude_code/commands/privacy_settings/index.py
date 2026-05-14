"""Command descriptor for /privacy. Ported from commands/privacy_settings/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "privacy"
DESCRIPTION = "Manage privacy settings"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class PrivacySettingsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /privacy command."""
        return {"type": "text", "value": f"/privacy not yet implemented"}


default = PrivacySettingsCommand()
