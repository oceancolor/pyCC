"""backfill_sessions command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "backfill-sessions"
DESCRIPTION = "Backfill session data (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/backfill-sessions not yet implemented"}
