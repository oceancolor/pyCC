"""MCP string utilities. Ported from services/mcp/mcpStringUtils.ts"""
from __future__ import annotations


def to_mcp_tool_name(server_name: str, tool_name: str) -> str:
    safe_server = server_name.replace("-", "_")
    return f"mcp__{safe_server}__{tool_name}"


def from_mcp_tool_name(full_name: str) -> tuple:
    if not full_name.startswith("mcp__"):
        return None, full_name
    rest = full_name[5:]
    sep = rest.find("__")
    if sep == -1:
        return rest, ""
    return rest[:sep], rest[sep + 2:]
