"""share command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "share"
DESCRIPTION = "Share the current conversation (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/share not yet implemented"}
