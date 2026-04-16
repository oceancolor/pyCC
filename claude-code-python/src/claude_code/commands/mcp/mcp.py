"""MCP command implementation. Ported from commands/mcp/."""
from __future__ import annotations
from typing import Any

async def call(args: str, context: Any = None) -> dict:
    parts = args.strip().split(None, 1)
    sub = parts[0] if parts else "list"
    if sub == "list":
        return {"type": "text", "value": "MCP servers: (none configured)"}
    if sub == "add":
        return {"type": "text", "value": f"Usage: /mcp add <name> <command> [args...]"}
    if sub == "remove":
        return {"type": "text", "value": f"Usage: /mcp remove <name>"}
    return {"type": "text", "value": f"Unknown mcp subcommand: {sub}. Use: list, add, remove"}
