"""
Ported from: commands/mcp/addCommand.ts (280 lines)

MCP add CLI subcommand implementation.
Registers the `mcp add` subcommand which adds MCP server configurations
(stdio, sse, or http transport) to the Claude Code config.

Commander.js replaced by argparse-style logic using a plain dict/argparse.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Stub imports — real implementations live in services/mcp/
# ---------------------------------------------------------------------------

def _cli_error(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(1)


def _cli_ok(message: str) -> None:
    sys.stdout.write(message + "\n")


def _ensure_config_scope(scope: Optional[str]) -> str:
    valid = {"local", "user", "project"}
    if scope not in valid:
        _cli_error(f"Error: Invalid scope '{scope}'. Must be one of: {', '.join(sorted(valid))}")
    return scope  # type: ignore[return-value]


def _ensure_transport(transport: Optional[str]) -> str:
    if transport is None:
        return "stdio"
    valid = {"stdio", "sse", "http"}
    if transport not in valid:
        _cli_error(f"Error: Invalid transport '{transport}'. Must be one of: stdio, sse, http")
    return transport  # type: ignore[return-value]


def _parse_headers(raw_headers: List[str]) -> Dict[str, str]:
    """Parse 'Key: Value' header strings into a dict."""
    headers: Dict[str, str] = {}
    for h in raw_headers:
        if ": " in h:
            k, _, v = h.partition(": ")
            headers[k.strip()] = v.strip()
        else:
            _cli_error(f"Error: Invalid header format '{h}'. Expected 'Key: Value'")
    return headers


def _parse_env_vars(raw_env: Optional[List[str]]) -> Dict[str, str]:
    if not raw_env:
        return {}
    result: Dict[str, str] = {}
    for e in raw_env:
        if "=" in e:
            k, _, v = e.partition("=")
            result[k.strip()] = v
        else:
            _cli_error(f"Error: Invalid env var format '{e}'. Expected 'KEY=value'")
    return result


async def _add_mcp_config(name: str, server_config: Dict[str, Any], scope: str) -> None:
    try:
        from claude_code.services.mcp.config import add_mcp_config
        await add_mcp_config(name, server_config, scope)
    except ImportError:
        # Stub: write config to a local JSON file
        import json
        config_path = os.path.join(os.path.expanduser("~"), ".claude", "mcp_servers.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        existing: Dict[str, Any] = {}
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing.setdefault(scope, {})[name] = server_config
        with open(config_path, "w") as f:
            json.dump(existing, f, indent=2)


async def _read_client_secret() -> Optional[str]:
    """Read OAuth client secret from stdin or MCP_CLIENT_SECRET env var."""
    secret = os.environ.get("MCP_CLIENT_SECRET")
    if secret:
        return secret
    try:
        import getpass
        return getpass.getpass("OAuth client secret: ")
    except Exception:
        return None


def _save_mcp_client_secret(
    name: str,
    server_config: Dict[str, Any],
    client_secret: str,
) -> None:
    try:
        from claude_code.services.mcp.auth import save_mcp_client_secret
        save_mcp_client_secret(name, server_config, client_secret)
    except ImportError:
        pass  # Non-fatal — secret management is optional in port


def _describe_mcp_config_file_path(scope: str) -> str:
    try:
        from claude_code.services.mcp.utils import describe_mcp_config_file_path
        return describe_mcp_config_file_path(scope)
    except ImportError:
        return f"~/.claude/mcp_{scope}.json"


def _is_xaa_enabled() -> bool:
    return os.environ.get("CLAUDE_CODE_ENABLE_XAA", "") == "1"


def _get_xaa_idp_settings() -> Optional[Dict[str, Any]]:
    try:
        from claude_code.services.mcp.xaa_idp_login import get_xaa_idp_settings
        return get_xaa_idp_settings()
    except ImportError:
        return None


def _log_event(event: str, data: Dict[str, Any]) -> None:
    try:
        from claude_code.services.analytics.index import log_event
        log_event(event, data)
    except (ImportError, Exception):
        pass


# ---------------------------------------------------------------------------
# Main add-command implementation
# ---------------------------------------------------------------------------

async def run_mcp_add(
    name: str,
    command_or_url: str,
    args: Optional[List[str]] = None,
    *,
    scope: str = "local",
    transport: Optional[str] = None,
    env: Optional[List[str]] = None,
    header: Optional[List[str]] = None,
    client_id: Optional[str] = None,
    client_secret: bool = False,
    callback_port: Optional[str] = None,
    xaa: bool = False,
) -> None:
    """
    Core logic for `mcp add` command.
    Mirrors the Commander.js action handler from addCommand.ts.
    """
    actual_command = command_or_url
    actual_args: List[str] = args or []

    if not name:
        _cli_error(
            "Error: Server name is required.\n"
            "Usage: claude mcp add <name> <command> [args...]"
        )
        return
    if not actual_command:
        _cli_error(
            "Error: Command is required when server name is provided.\n"
            "Usage: claude mcp add <name> <command> [args...]"
        )
        return

    resolved_scope = _ensure_config_scope(scope)
    resolved_transport = _ensure_transport(transport)

    # XAA validation
    if xaa and not _is_xaa_enabled():
        _cli_error("Error: --xaa requires CLAUDE_CODE_ENABLE_XAA=1 in your environment")
        return

    if xaa:
        missing: List[str] = []
        if not client_id:
            missing.append("--client-id")
        if not client_secret:
            missing.append("--client-secret")
        if not _get_xaa_idp_settings():
            missing.append("'claude mcp xaa setup' (settings.xaaIdp not configured)")
        if missing:
            _cli_error(f"Error: --xaa requires: {', '.join(missing)}")
            return

    transport_explicit = transport is not None
    looks_like_url = (
        actual_command.startswith("http://")
        or actual_command.startswith("https://")
        or actual_command.startswith("localhost")
        or actual_command.endswith("/sse")
        or actual_command.endswith("/mcp")
    )

    _log_event(
        "tengu_mcp_add",
        {
            "type": resolved_transport,
            "scope": resolved_scope,
            "source": "command",
            "transport": resolved_transport,
            "transportExplicit": transport_explicit,
            "looksLikeUrl": looks_like_url,
        },
    )

    if resolved_transport == "sse":
        if not actual_command:
            _cli_error("Error: URL is required for SSE transport.")
            return

        parsed_headers = _parse_headers(header) if header else None
        callback_port_int = int(callback_port) if callback_port else None
        oauth = None
        if client_id or callback_port_int or xaa:
            oauth = {}
            if client_id:
                oauth["clientId"] = client_id
            if callback_port_int:
                oauth["callbackPort"] = callback_port_int
            if xaa:
                oauth["xaa"] = True

        resolved_secret: Optional[str] = None
        if client_secret and client_id:
            resolved_secret = await _read_client_secret()

        server_config: Dict[str, Any] = {
            "type": "sse",
            "url": actual_command,
        }
        if parsed_headers:
            server_config["headers"] = parsed_headers
        if oauth:
            server_config["oauth"] = oauth

        await _add_mcp_config(name, server_config, resolved_scope)

        if resolved_secret:
            _save_mcp_client_secret(name, server_config, resolved_secret)

        sys.stdout.write(
            f"Added SSE MCP server {name} with URL: {actual_command} "
            f"to {resolved_scope} config\n"
        )
        if parsed_headers:
            import json
            sys.stdout.write(f"Headers: {json.dumps(parsed_headers, indent=2)}\n")

    elif resolved_transport == "http":
        if not actual_command:
            _cli_error("Error: URL is required for HTTP transport.")
            return

        parsed_headers = _parse_headers(header) if header else None
        callback_port_int = int(callback_port) if callback_port else None
        oauth = None
        if client_id or callback_port_int or xaa:
            oauth = {}
            if client_id:
                oauth["clientId"] = client_id
            if callback_port_int:
                oauth["callbackPort"] = callback_port_int
            if xaa:
                oauth["xaa"] = True

        resolved_secret = None
        if client_secret and client_id:
            resolved_secret = await _read_client_secret()

        server_config = {
            "type": "http",
            "url": actual_command,
        }
        if parsed_headers:
            server_config["headers"] = parsed_headers
        if oauth:
            server_config["oauth"] = oauth

        await _add_mcp_config(name, server_config, resolved_scope)

        if resolved_secret:
            _save_mcp_client_secret(name, server_config, resolved_secret)

        sys.stdout.write(
            f"Added HTTP MCP server {name} with URL: {actual_command} "
            f"to {resolved_scope} config\n"
        )
        if parsed_headers:
            import json
            sys.stdout.write(f"Headers: {json.dumps(parsed_headers, indent=2)}\n")

    else:
        # stdio transport
        if any([client_id, client_secret, callback_port, xaa]):
            sys.stderr.write(
                "Warning: --client-id, --client-secret, --callback-port, and --xaa "
                "are only supported for HTTP/SSE transports and will be ignored for stdio.\n"
            )

        if not transport_explicit and looks_like_url:
            sys.stderr.write(
                f'\nWarning: The command "{actual_command}" looks like a URL, '
                "but is being interpreted as a stdio server as --transport was not specified.\n"
            )
            sys.stderr.write(
                f"If this is an HTTP server, use: claude mcp add --transport http {name} {actual_command}\n"
            )
            sys.stderr.write(
                f"If this is an SSE server, use: claude mcp add --transport sse {name} {actual_command}\n"
            )

        parsed_env = _parse_env_vars(env)
        server_config = {
            "type": "stdio",
            "command": actual_command,
            "args": actual_args,
            "env": parsed_env,
        }
        await _add_mcp_config(name, server_config, resolved_scope)

        args_str = " ".join(actual_args)
        sys.stdout.write(
            f"Added stdio MCP server {name} with command: "
            f"{actual_command} {args_str} to {resolved_scope} config\n"
        )

    _cli_ok(f"File modified: {_describe_mcp_config_file_path(resolved_scope)}")


def register_mcp_add_command(subparsers: Any) -> None:
    """
    Register the `mcp add` subcommand with an argparse subparser group.
    Mirrors registerMcpAddCommand() from the TS source.
    """
    try:
        import argparse

        parser = subparsers.add_parser(
            "add",
            help="Add an MCP server to Claude Code.",
            description=(
                "Add an MCP server to Claude Code.\n\n"
                "Examples:\n"
                "  claude mcp add --transport http sentry https://mcp.sentry.dev/mcp\n"
                "  claude mcp add -e API_KEY=xxx my-server -- npx my-mcp-server"
            ),
        )
        parser.add_argument("name", help="Server name")
        parser.add_argument("command_or_url", metavar="commandOrUrl", help="Command or URL")
        parser.add_argument("args", nargs="*", help="Additional arguments")
        parser.add_argument("-s", "--scope", default="local",
                            help="Config scope (local, user, project)")
        parser.add_argument("-t", "--transport",
                            help="Transport type (stdio, sse, http)")
        parser.add_argument("-e", "--env", action="append",
                            help="Set environment variables (KEY=value)")
        parser.add_argument("-H", "--header", action="append",
                            help="Set WebSocket headers (Key: Value)")
        parser.add_argument("--client-id", dest="client_id",
                            help="OAuth client ID")
        parser.add_argument("--client-secret", dest="client_secret",
                            action="store_true",
                            help="Prompt for OAuth client secret")
        parser.add_argument("--callback-port", dest="callback_port",
                            help="Fixed port for OAuth callback")
        if _is_xaa_enabled():
            parser.add_argument("--xaa", action="store_true",
                                help="Enable XAA (SEP-990) for this server")
        parser.set_defaults(handler=_handle_add_args)
    except Exception:
        pass


async def _handle_add_args(parsed_args: Any) -> None:
    """Translate parsed argparse namespace to run_mcp_add() kwargs."""
    await run_mcp_add(
        name=parsed_args.name,
        command_or_url=parsed_args.command_or_url,
        args=parsed_args.args,
        scope=parsed_args.scope,
        transport=getattr(parsed_args, "transport", None),
        env=getattr(parsed_args, "env", None),
        header=getattr(parsed_args, "header", None),
        client_id=getattr(parsed_args, "client_id", None),
        client_secret=getattr(parsed_args, "client_secret", False),
        callback_port=getattr(parsed_args, "callback_port", None),
        xaa=getattr(parsed_args, "xaa", False),
    )
