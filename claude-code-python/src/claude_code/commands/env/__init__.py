"""env command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "env"
DESCRIPTION = "Show environment variables (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "local-command", "name": "env", "args": args}
