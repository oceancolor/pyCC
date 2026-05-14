"""Command descriptor for /login. Ported from commands/login/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "login"
DESCRIPTION = "Sign in with your Anthropic account"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class LoginCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /login command."""
        return {"type": "text", "value": f"/login not yet implemented"}


default = LoginCommand()
