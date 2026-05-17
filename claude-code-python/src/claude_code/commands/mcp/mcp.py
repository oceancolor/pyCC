"""MCP command implementation. Ported from commands/mcp/mcp.tsx (headless Python version).

The original TypeScript uses React/Ink for rendering. This Python version
provides the same business logic but returns structured dicts rather than
React nodes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_mcp_clients(context: Any) -> List[Dict[str, Any]]:
    """Extract MCP clients from context / app state."""
    if context is None:
        return []
    # Direct attribute
    clients = getattr(context, "mcp_clients", None)
    if clients is not None:
        return list(clients)
    # Via app state
    get_app_state = getattr(context, "get_app_state", None)
    if callable(get_app_state):
        try:
            state = get_app_state()
            mcp = (state or {}).get("mcp") or {}
            return list(mcp.get("clients") or [])
        except Exception:
            pass
    return []


def _client_name(client: Any) -> str:
    if isinstance(client, dict):
        return client.get("name", "")
    return getattr(client, "name", "")


def _client_type(client: Any) -> str:
    if isinstance(client, dict):
        return client.get("type", "")
    return getattr(client, "type", "")


def _toggle_mcp_server(context: Any, name: str) -> bool:
    """
    Toggle a single MCP server's enabled state.
    Returns True if the toggle succeeded (i.e. found and toggled).
    """
    try:
        from claude_code.services.mcp.connection_manager import toggle_mcp_enabled  # type: ignore[import]
        toggle_mcp_enabled(name)
        return True
    except (ImportError, Exception):
        pass

    # Fallback: mutate app state directly
    set_app_state = getattr(context, "set_app_state", None) if context else None
    if not callable(set_app_state):
        return False

    toggled = [False]

    def _updater(prev: dict) -> dict:
        mcp = dict(prev.get("mcp") or {})
        clients = list(mcp.get("clients") or [])
        new_clients = []
        for c in clients:
            c_name = _client_name(c)
            if c_name == name:
                toggled[0] = True
                c_type = _client_type(c)
                new_type = "disabled" if c_type != "disabled" else "stdio"
                if isinstance(c, dict):
                    new_clients.append({**c, "type": new_type})
                else:
                    new_clients.append(c)
            else:
                new_clients.append(c)
        return {**prev, "mcp": {**mcp, "clients": new_clients}}

    set_app_state(_updater)
    return toggled[0]


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

async def _handle_list(clients: List[Any]) -> Dict[str, Any]:
    """Handle /mcp or /mcp list."""
    if not clients:
        return {"type": "text", "value": "No MCP servers configured."}

    lines = ["MCP servers:"]
    for c in clients:
        name = _client_name(c)
        ctype = _client_type(c)
        status = "disabled" if ctype == "disabled" else "enabled"
        lines.append(f"  • {name} ({status})")
    return {"type": "text", "value": "\n".join(lines)}


async def _handle_enable_disable(
    action: str,
    target: str,
    clients: List[Any],
    context: Any,
) -> Dict[str, Any]:
    """Handle /mcp enable [target] or /mcp disable [target]."""
    is_enabling = action == "enable"
    # Filter out IDE client (matches TS behaviour)
    clients = [c for c in clients if _client_name(c) != "ide"]

    if target == "all":
        to_toggle = [
            c for c in clients
            if (is_enabling and _client_type(c) == "disabled")
            or (not is_enabling and _client_type(c) != "disabled")
        ]
    else:
        to_toggle = [c for c in clients if _client_name(c) == target]

    if not to_toggle:
        if target == "all":
            msg = f"All MCP servers are already {'enabled' if is_enabling else 'disabled'}."
        else:
            msg = f'MCP server "{target}" not found.'
        return {"type": "text", "value": msg}

    for c in to_toggle:
        _toggle_mcp_server(context, _client_name(c))

    if target == "all":
        msg = f"{'Enabled' if is_enabling else 'Disabled'} {len(to_toggle)} MCP server(s)."
    else:
        msg = f'MCP server "{target}" {"enabled" if is_enabling else "disabled"}.'
    return {"type": "text", "value": msg}


async def _handle_reconnect(server_name: str, context: Any) -> Dict[str, Any]:
    """Handle /mcp reconnect <server>."""
    try:
        from claude_code.services.mcp.connection_manager import reconnect_mcp_server  # type: ignore[import]
        await reconnect_mcp_server(server_name)
        return {"type": "text", "value": f'MCP server "{server_name}" reconnected.'}
    except (ImportError, Exception) as exc:
        return {"type": "text", "value": f'Failed to reconnect "{server_name}": {exc}'}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def call(args: str = "", context: Any = None) -> Dict[str, Any]:
    """
    Handle the /mcp command.

    Supported sub-commands:
      /mcp [list]            — List all configured MCP servers.
      /mcp enable [name|all] — Enable one or all MCP servers.
      /mcp disable [name|all]— Disable one or all MCP servers.
      /mcp reconnect <name>  — Reconnect a specific MCP server.

    Returns a ``{"type": "text", "value": ...}`` dict.
    """
    clients = _get_mcp_clients(context)
    parts = (args or "").strip().split()

    if not parts or parts[0] in ("list", "no-redirect"):
        return await _handle_list(clients)

    sub = parts[0]

    if sub in ("enable", "disable"):
        target = " ".join(parts[1:]) if len(parts) > 1 else "all"
        return await _handle_enable_disable(sub, target, clients, context)

    if sub == "reconnect" and len(parts) > 1:
        server_name = " ".join(parts[1:])
        return await _handle_reconnect(server_name, context)

    # Unknown sub-command
    return {
        "type": "text",
        "value": (
            f"Unknown /mcp sub-command: {sub}\n"
            "Usage: /mcp [list|enable|disable [server]|reconnect <server>]"
        ),
    }
