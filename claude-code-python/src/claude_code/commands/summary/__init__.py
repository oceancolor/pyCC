"""summary command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "summary"
DESCRIPTION = "Generate a summary of the current conversation (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/summary not yet implemented"}
