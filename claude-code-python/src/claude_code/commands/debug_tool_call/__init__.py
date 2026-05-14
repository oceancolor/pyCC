"""debug_tool_call command package stub (ANT-internal)."""
from __future__ import annotations

NAME = "debug-tool-call"
DESCRIPTION = "Debug a tool call (ANT-only)"
TYPE = "local"


async def call(args: str = "", context=None) -> dict:
    return {"type": "local-command", "name": "debug-tool-call", "args": args}
