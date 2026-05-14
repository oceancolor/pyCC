"""ant_trace command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "ant-trace"
DESCRIPTION = "Trace ANT-internal events (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/ant-trace not yet implemented"}
