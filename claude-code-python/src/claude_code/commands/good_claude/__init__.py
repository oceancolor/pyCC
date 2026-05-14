"""good_claude command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "good-claude"
DESCRIPTION = "Send positive feedback to improve Claude (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "local-command", "name": "good-claude", "args": args}
