"""autofix_pr command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "autofix-pr"
DESCRIPTION = "Automatically fix a PR (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "local-command", "name": "autofix-pr", "args": args}
