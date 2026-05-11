"""
Pure string utility functions for MCP tool/server name parsing.
Ported from services/mcp/mcpStringUtils.ts

This module has no heavy dependencies to keep it lightweight for
consumers that only need string parsing (e.g., permissionValidation).
"""
from __future__ import annotations

import re


def normalize_name_for_mcp(name: str) -> str:
    """Normalize a name for use in MCP identifiers (replace non-alphanumeric with _)."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def mcp_info_from_string(
    tool_string: str,
) -> dict | None:
    """
    Extracts MCP server information from a tool name string.

    Expected format: "mcp__serverName__toolName"
    Returns a dict with serverName and optional toolName, or None if not valid.

    Known limitation: If a server name contains "__", parsing will be incorrect.
    """
    parts = tool_string.split("__")
    if len(parts) < 2:
        return None
    mcp_part = parts[0]
    if mcp_part != "mcp":
        return None
    server_name = parts[1] if len(parts) > 1 else None
    if not server_name:
        return None
    # Join all parts after server name to preserve double underscores in tool names
    tool_name_parts = parts[2:]
    tool_name = "__".join(tool_name_parts) if tool_name_parts else None
    return {"serverName": server_name, "toolName": tool_name}


def get_mcp_prefix(server_name: str) -> str:
    """
    Generates the MCP tool/command name prefix for a given server.

    :param server_name: Name of the MCP server
    :returns: The prefix string, e.g. "mcp__my_server__"
    """
    return f"mcp__{normalize_name_for_mcp(server_name)}__"


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """
    Builds a fully qualified MCP tool name from server and tool names.
    Inverse of mcp_info_from_string().

    :param server_name: Name of the MCP server (unnormalized)
    :param tool_name: Name of the tool (unnormalized)
    :returns: The fully qualified name, e.g., "mcp__server__tool"
    """
    return f"{get_mcp_prefix(server_name)}{normalize_name_for_mcp(tool_name)}"


def get_tool_name_for_permission_check(
    tool_name: str,
    mcp_info: dict | None = None,
) -> str:
    """
    Returns the name to use for permission rule matching.

    For MCP tools, uses the fully qualified mcp__server__tool name so that
    deny rules targeting builtins don't match unprefixed MCP replacements
    that share the same display name. Falls back to tool_name.

    :param tool_name: The base tool name
    :param mcp_info: Optional dict with 'serverName' and 'toolName' keys
    :returns: The permission-check name
    """
    if mcp_info and mcp_info.get("serverName") and mcp_info.get("toolName"):
        return build_mcp_tool_name(mcp_info["serverName"], mcp_info["toolName"])
    return tool_name


def get_mcp_display_name(full_name: str, server_name: str) -> str:
    """
    Extracts the display name from an MCP tool/command name.

    :param full_name: The full MCP tool/command name (e.g., "mcp__server_name__tool_name")
    :param server_name: The server name to remove from the prefix
    :returns: The display name without the MCP prefix
    """
    prefix = f"mcp__{normalize_name_for_mcp(server_name)}__"
    return full_name.replace(prefix, "", 1)


def extract_mcp_tool_display_name(user_facing_name: str) -> str:
    """
    Extracts just the tool/command display name from a userFacingName.

    :param user_facing_name: The full user-facing name
        (e.g., "github - Add comment to issue (MCP)")
    :returns: The display name without server prefix and (MCP) suffix
    """
    # Remove the (MCP) suffix if present
    without_suffix = re.sub(r"\s*\(MCP\)\s*$", "", user_facing_name).strip()

    # Remove the server prefix (everything before " - ")
    dash_index = without_suffix.find(" - ")
    if dash_index != -1:
        return without_suffix[dash_index + 3:].strip()

    return without_suffix


# Backwards-compatible aliases (from the old stub)
def to_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Alias for build_mcp_tool_name."""
    return build_mcp_tool_name(server_name, tool_name)


def from_mcp_tool_name(full_name: str) -> tuple:
    """
    Parse an MCP tool name into (server_name, tool_name).
    Returns (None, full_name) if not a valid MCP tool name.
    """
    info = mcp_info_from_string(full_name)
    if info is None:
        return None, full_name
    return info["serverName"], info["toolName"] or ""
