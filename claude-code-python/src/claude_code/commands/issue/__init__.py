"""issue command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "issue"
DESCRIPTION = "Create a GitHub issue (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "local-command", "name": "issue", "args": args}
