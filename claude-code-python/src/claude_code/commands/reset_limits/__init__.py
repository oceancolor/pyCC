"""reset_limits command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "reset-limits"
DESCRIPTION = "Reset usage limits (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/reset-limits not yet implemented"}
