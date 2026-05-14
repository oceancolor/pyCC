"""break_cache command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "break-cache"
DESCRIPTION = "Break the prompt cache (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/break-cache not yet implemented"}
