"""
Ported from: commands/mcp/mcp.tsx (list subcommand logic) and the broader MCP
command structure (addCommand.ts / the index.ts pattern).

`list_command` — list all configured MCP servers, their transport, and status.
There is no dedicated `listCommand.ts` in the TS source; instead the listing
is handled inside the interactive MCPSettings UI.  This Python module provides
a CLI-friendly list function mirroring the data that MCPSettings would display.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _get_mcp_configs() -> Dict[str, List[Dict[str, Any]]]:
    """
    Return all configured MCP servers grouped by scope.

    Returns a dict like::
        {
          "local": [ {"name": "...", "type": "stdio", ...}, ... ],
          "user":  [ ... ],
          "project": [ ... ],
        }
    """
    try:
        from claude_code.services.mcp.config import get_all_mcp_configs  # type: ignore[import]
        return get_all_mcp_configs()
    except ImportError:
        pass

    # Fallback: read from the stub JSON file written by add_command.py
    config_path = os.path.join(os.path.expanduser("~"), ".claude", "mcp_servers.json")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def _get_mcp_clients() -> List[Dict[str, Any]]:
    """
    Return the currently connected (runtime) MCP clients.
    """
    try:
        from claude_code.services.mcp.mcp_connection_manager import get_mcp_clients  # type: ignore[import]
        return get_mcp_clients()
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_server(name: str, cfg: Dict[str, Any]) -> str:
    transport = cfg.get("type", "stdio")
    if transport in ("sse", "http"):
        detail = cfg.get("url", "")
    else:
        cmd = cfg.get("command", "")
        args = " ".join(cfg.get("args", []))
        detail = f"{cmd} {args}".strip()
    return f"  • {name} [{transport}]  {detail}"


def _format_scope_block(scope: str, servers: Dict[str, Any]) -> str:
    if not servers:
        return ""
    lines = [f"{scope.upper()} scope:"]
    for name, cfg in servers.items():
        if isinstance(cfg, dict):
            lines.append(_format_server(name, cfg))
        else:
            lines.append(f"  • {name}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_mcp_list(scope: Optional[str] = None) -> None:
    """
    Print a human-readable list of configured MCP servers to stdout.

    Parameters
    ----------
    scope:
        If provided, restrict output to this scope (local/user/project).
    """
    all_configs = _get_mcp_configs()

    if not all_configs:
        sys.stdout.write("No MCP servers configured.\n")
        return

    blocks: List[str] = []
    for sc, servers in all_configs.items():
        if scope and sc != scope:
            continue
        if isinstance(servers, dict):
            block = _format_scope_block(sc, servers)
        elif isinstance(servers, list):
            # List of server objects with "name" field
            servers_dict = {s.get("name", i): s for i, s in enumerate(servers)}
            block = _format_scope_block(sc, servers_dict)
        else:
            continue
        if block:
            blocks.append(block)

    if blocks:
        sys.stdout.write("\n\n".join(blocks) + "\n")
    else:
        sys.stdout.write(
            f"No MCP servers configured for scope '{scope}'.\n"
            if scope
            else "No MCP servers configured.\n"
        )


def register_mcp_list_command(subparsers: Any) -> None:
    """Register the ``mcp list`` subcommand on an argparse subparser group."""
    try:
        parser = subparsers.add_parser(
            "list",
            help="List configured MCP servers.",
        )
        parser.add_argument(
            "-s", "--scope",
            default=None,
            help="Restrict to a specific scope (local, user, project).",
        )
        parser.set_defaults(handler=_handle_list_args)
    except Exception:  # noqa: BLE001
        pass


def _handle_list_args(parsed_args: Any) -> None:
    run_mcp_list(scope=getattr(parsed_args, "scope", None))
