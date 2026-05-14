"""Command descriptor for /oauth-refresh. Ported from commands/oauth_refresh/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "oauth-refresh"
DESCRIPTION = "Force OAuth token refresh (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class OauthRefreshCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /oauth-refresh command."""
        return {"type": "local-command", "name": "oauth-refresh", "args": args}


default = OauthRefreshCommand()
