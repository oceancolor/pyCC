"""Logout command package."""
from __future__ import annotations
from typing import Literal
from dataclasses import dataclass

NAME = "logout"
DESCRIPTION = "Sign out from your Anthropic account"
TYPE: Literal["local-jsx"] = "local-jsx"


@dataclass
class LogoutCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /logout command."""
        return {"type": "text", "value": "/logout not yet implemented"}


default = LogoutCommand()
