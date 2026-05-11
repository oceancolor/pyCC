"""
Ported from: commands/mcp/addCommand.ts (remove logic) and the broader MCP
command structure.

`remove_command` — remove an MCP server from the Claude Code config.
There is no dedicated `removeCommand.ts` in the TS source; removal is handled
by `removeMcpConfig` in services/mcp/config.ts invoked from the interactive
MCPSettings UI.  This module provides a CLI-friendly implementation.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _cli_error(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(1)


def _cli_ok(message: str) -> None:
    sys.stdout.write(message + "\n")


def _ensure_config_scope(scope: Optional[str]) -> str:
    valid = {"local", "user", "project"}
    if scope not in valid:
        _cli_error(
            f"Error: Invalid scope '{scope}'. Must be one of: {', '.join(sorted(valid))}"
        )
    return scope  # type: ignore[return-value]


def _describe_mcp_config_file_path(scope: str) -> str:
    try:
        from claude_code.services.mcp.utils import describe_mcp_config_file_path  # type: ignore[import]
        return describe_mcp_config_file_path(scope)
    except ImportError:
        return f"~/.claude/mcp_{scope}.json"


def _log_event(event: str, data: Dict[str, Any]) -> None:
    try:
        from claude_code.services.analytics.index import log_event  # type: ignore[import]
        log_event(event, data)
    except (ImportError, Exception):
        pass


# ---------------------------------------------------------------------------
# Core removal logic
# ---------------------------------------------------------------------------

async def _remove_mcp_config(name: str, scope: str) -> bool:
    """
    Remove the server *name* from *scope*.

    Returns True if the server was found and removed, False otherwise.
    """
    try:
        from claude_code.services.mcp.config import remove_mcp_config  # type: ignore[import]
        return await remove_mcp_config(name, scope)
    except ImportError:
        pass

    # Fallback: manipulate the stub JSON file
    config_path = os.path.join(os.path.expanduser("~"), ".claude", "mcp_servers.json")
    if not os.path.exists(config_path):
        return False

    try:
        with open(config_path, encoding="utf-8") as fh:
            existing: Dict[str, Any] = json.load(fh)
    except Exception:  # noqa: BLE001
        return False

    scope_data = existing.get(scope, {})
    if name not in scope_data:
        return False

    del scope_data[name]
    existing[scope] = scope_data

    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)
    return True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def run_mcp_remove(
    name: str,
    *,
    scope: str = "local",
) -> None:
    """
    Remove the MCP server *name* from *scope*.

    Mirrors the remove action that MCPSettings calls in the interactive UI.
    """
    if not name:
        _cli_error(
            "Error: Server name is required.\n"
            "Usage: claude mcp remove <name> [-s scope]"
        )
        return

    resolved_scope = _ensure_config_scope(scope)

    _log_event(
        "tengu_mcp_remove",
        {
            "scope": resolved_scope,
            "source": "command",
        },
    )

    found = await _remove_mcp_config(name, resolved_scope)

    if found:
        _cli_ok(
            f"Removed MCP server '{name}' from {resolved_scope} config.\n"
            f"File modified: {_describe_mcp_config_file_path(resolved_scope)}"
        )
    else:
        _cli_error(
            f"Error: MCP server '{name}' not found in {resolved_scope} config."
        )


def register_mcp_remove_command(subparsers: Any) -> None:
    """Register the ``mcp remove`` subcommand on an argparse subparser group."""
    try:
        parser = subparsers.add_parser(
            "remove",
            aliases=["rm"],
            help="Remove an MCP server from Claude Code.",
        )
        parser.add_argument("name", help="Server name to remove")
        parser.add_argument(
            "-s", "--scope",
            default="local",
            help="Configuration scope (local, user, project)",
        )
        parser.set_defaults(handler=_handle_remove_args)
    except Exception:  # noqa: BLE001
        pass


async def _handle_remove_args(parsed_args: Any) -> None:
    await run_mcp_remove(
        name=parsed_args.name,
        scope=parsed_args.scope,
    )
