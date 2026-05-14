"""bughunter command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "bughunter"
DESCRIPTION = "Start a bug hunting session (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/bughunter not yet implemented"}
