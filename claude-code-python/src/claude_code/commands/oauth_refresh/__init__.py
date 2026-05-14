"""oauth_refresh command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "oauth-refresh"
DESCRIPTION = "Force OAuth token refresh (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/oauth-refresh not yet implemented"}
