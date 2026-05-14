"""ctx_viz command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "ctx-viz"
DESCRIPTION = "Visualize context usage in detail (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/ctx-viz not yet implemented"}
