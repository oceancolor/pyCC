"""perf_issue command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "perf-issue"
DESCRIPTION = "Report a performance issue (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "text", "value": "/perf-issue not yet implemented"}
