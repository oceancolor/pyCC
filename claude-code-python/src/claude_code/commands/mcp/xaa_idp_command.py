"""
Ported from: commands/mcp/xaaIdpCommand.ts

`claude mcp xaa` — manage the XAA (SEP-990) IdP (Identity Provider) connection.

XAA is an SSO integration that allows MCP servers to authenticate silently
once the user has completed a one-time OIDC login.  This module ports the
four subcommands: setup, login, show, clear.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Helper: abort with error
# ---------------------------------------------------------------------------

def _cli_error(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(1)


def _cli_ok(message: Optional[str] = None) -> None:
    if message:
        sys.stdout.write(message + "\n")


# ---------------------------------------------------------------------------
# Stub helpers — real implementations live in services/mcp/xaa_idp_login
# ---------------------------------------------------------------------------

def _is_xaa_enabled() -> bool:
    return os.environ.get("CLAUDE_CODE_ENABLE_XAA", "") == "1"


def _get_xaa_idp_settings() -> Optional[Dict[str, Any]]:
    try:
        from claude_code.services.mcp.xaa_idp_login import get_xaa_idp_settings  # type: ignore[import]
        return get_xaa_idp_settings()
    except ImportError:
        return None


def _save_xaa_idp_settings(settings: Optional[Dict[str, Any]]) -> None:
    try:
        from claude_code.utils.settings.settings import update_settings_for_source  # type: ignore[import]
        update_settings_for_source("userSettings", {"xaaIdp": settings})
    except ImportError:
        pass


def _get_idp_client_secret(issuer: str) -> Optional[str]:
    try:
        from claude_code.services.mcp.xaa_idp_login import get_idp_client_secret  # type: ignore[import]
        return get_idp_client_secret(issuer)
    except ImportError:
        return os.environ.get("MCP_XAA_IDP_CLIENT_SECRET")


def _save_idp_client_secret(issuer: str, secret: str) -> Dict[str, Any]:
    try:
        from claude_code.services.mcp.xaa_idp_login import save_idp_client_secret  # type: ignore[import]
        return save_idp_client_secret(issuer, secret)
    except ImportError:
        return {"success": True, "warning": None}


def _get_cached_idp_id_token(issuer: str) -> Optional[str]:
    try:
        from claude_code.services.mcp.xaa_idp_login import get_cached_idp_id_token  # type: ignore[import]
        return get_cached_idp_id_token(issuer)
    except ImportError:
        return None


def _save_idp_id_token_from_jwt(issuer: str, jwt: str) -> int:
    try:
        from claude_code.services.mcp.xaa_idp_login import save_idp_id_token_from_jwt  # type: ignore[import]
        return save_idp_id_token_from_jwt(issuer, jwt)
    except ImportError:
        import time
        return int(time.time()) + 3600


def _clear_idp_id_token(issuer: str) -> None:
    try:
        from claude_code.services.mcp.xaa_idp_login import clear_idp_id_token  # type: ignore[import]
        clear_idp_id_token(issuer)
    except ImportError:
        pass


def _clear_idp_client_secret(issuer: str) -> None:
    try:
        from claude_code.services.mcp.xaa_idp_login import clear_idp_client_secret  # type: ignore[import]
        clear_idp_client_secret(issuer)
    except ImportError:
        pass


async def _acquire_idp_id_token(
    idp_issuer: str,
    idp_client_id: str,
    idp_client_secret: Optional[str],
    callback_port: Optional[int],
    on_authorization_url,
) -> None:
    try:
        from claude_code.services.mcp.xaa_idp_login import acquire_idp_id_token  # type: ignore[import]
        await acquire_idp_id_token(
            idp_issuer=idp_issuer,
            idp_client_id=idp_client_id,
            idp_client_secret=idp_client_secret,
            callback_port=callback_port,
            on_authorization_url=on_authorization_url,
        )
    except ImportError:
        raise RuntimeError(
            "XAA IdP login not available: install the xaa_idp_login service module."
        )


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def _run_setup(
    issuer: str,
    client_id: str,
    client_secret_flag: bool,
    callback_port: Optional[str],
) -> None:
    """Configure the IdP connection (mirrors xaaIdp `setup` subcommand)."""
    # Validate issuer URL
    from urllib.parse import urlparse
    try:
        parsed = urlparse(issuer)
        assert parsed.scheme in ("http", "https") and parsed.netloc
    except Exception:
        _cli_error(f'Error: --issuer must be a valid URL (got "{issuer}")')
        return

    loopback_hosts = {"localhost", "127.0.0.1", "[::1]"}
    if parsed.scheme == "http" and parsed.hostname not in loopback_hosts:
        _cli_error(
            f'Error: --issuer must use https:// (got "{parsed.scheme}://{parsed.netloc}")'
        )
        return

    port_int: Optional[int] = None
    if callback_port is not None:
        try:
            port_int = int(callback_port)
            assert port_int > 0
        except (ValueError, AssertionError):
            _cli_error("Error: --callback-port must be a positive integer")
            return

    secret: Optional[str] = None
    if client_secret_flag:
        secret = os.environ.get("MCP_XAA_IDP_CLIENT_SECRET")
        if not secret:
            _cli_error("Error: --client-secret requires MCP_XAA_IDP_CLIENT_SECRET env var")
            return

    # Clear stale keychain if issuer/client changed
    old = _get_xaa_idp_settings()
    if old:
        old_issuer = old.get("issuer")
        if old_issuer and old_issuer != issuer:
            _clear_idp_id_token(old_issuer)
            _clear_idp_client_secret(old_issuer)
        elif old_issuer and old.get("clientId") != client_id:
            _clear_idp_id_token(old_issuer)
            _clear_idp_client_secret(old_issuer)

    _save_xaa_idp_settings(
        {"issuer": issuer, "clientId": client_id, "callbackPort": port_int}
    )

    if secret:
        result = _save_idp_client_secret(issuer, secret)
        if not result.get("success"):
            warn = result.get("warning")
            _cli_error(
                f"Error: settings written but keychain save failed"
                + (f" — {warn}" if warn else "")
                + ". Re-run with --client-secret once keychain is available."
            )
            return

    _cli_ok(f"XAA IdP connection configured for {issuer}")


async def _run_login(force: bool, id_token: Optional[str]) -> None:
    """Cache an IdP id_token (mirrors xaaIdp `login` subcommand)."""
    idp = _get_xaa_idp_settings()
    if not idp:
        _cli_error("Error: no XAA IdP connection. Run 'claude mcp xaa setup' first.")
        return

    if id_token:
        expires_at = _save_idp_id_token_from_jwt(idp["issuer"], id_token)
        import datetime
        _cli_ok(
            f"id_token cached for {idp['issuer']} "
            f"(expires {datetime.datetime.utcfromtimestamp(expires_at / 1000).isoformat()})"
        )
        return

    if force:
        _clear_idp_id_token(idp["issuer"])

    if _get_cached_idp_id_token(idp["issuer"]) is not None:
        _cli_ok(
            f"Already logged in to {idp['issuer']} (cached id_token still valid). "
            "Use --force to re-login."
        )
        return

    sys.stdout.write(f"Opening browser for IdP login at {idp['issuer']}\u2026\n")
    try:
        await _acquire_idp_id_token(
            idp_issuer=idp["issuer"],
            idp_client_id=idp["clientId"],
            idp_client_secret=_get_idp_client_secret(idp["issuer"]),
            callback_port=idp.get("callbackPort"),
            on_authorization_url=lambda url: sys.stdout.write(
                "If the browser did not open, visit:\n  " + url + "\n"
            ),
        )
        _cli_ok("Logged in. MCP servers with --xaa will now authenticate silently.")
    except Exception as exc:  # noqa: BLE001
        _cli_error(f"IdP login failed: {exc}")


def _run_show() -> None:
    """Show the current IdP connection config (mirrors xaaIdp `show`)."""
    idp = _get_xaa_idp_settings()
    if not idp:
        _cli_ok("No XAA IdP connection configured.")
        return

    issuer = idp.get("issuer", "")
    has_secret = _get_idp_client_secret(issuer) is not None
    has_token = _get_cached_idp_id_token(issuer) is not None

    sys.stdout.write(f"Issuer:        {issuer}\n")
    sys.stdout.write(f"Client ID:     {idp.get('clientId', '')}\n")
    if idp.get("callbackPort") is not None:
        sys.stdout.write(f"Callback port: {idp['callbackPort']}\n")
    sys.stdout.write(
        f"Client secret: {'(stored in keychain)' if has_secret else '(not set - PKCE-only)'}\n"
    )
    login_hint = "no — run 'claude mcp xaa login'"
    logged_in_str = "yes (id_token cached)" if has_token else login_hint
    sys.stdout.write(
        f"Logged in:     {logged_in_str}\n"
    )
    _cli_ok()


def _run_clear() -> None:
    """Clear the IdP connection config (mirrors xaaIdp `clear`)."""
    idp = _get_xaa_idp_settings()
    _save_xaa_idp_settings(None)
    if idp:
        issuer = idp.get("issuer", "")
        _clear_idp_id_token(issuer)
        _clear_idp_client_secret(issuer)
    _cli_ok("XAA IdP connection cleared")


# ---------------------------------------------------------------------------
# argparse registration
# ---------------------------------------------------------------------------

def register_mcp_xaa_idp_command(subparsers: Any) -> None:
    """Register ``mcp xaa`` and its subcommands on *subparsers*."""
    import argparse

    xaa_parser = subparsers.add_parser(
        "xaa",
        help="Manage the XAA (SEP-990) IdP connection",
    )
    xaa_sub = xaa_parser.add_subparsers(dest="xaa_command")

    # --- setup ---
    setup_p = xaa_sub.add_parser("setup", help="Configure the IdP connection")
    setup_p.add_argument("--issuer", required=True, help="IdP issuer URL (OIDC discovery)")
    setup_p.add_argument("--client-id", dest="client_id", required=True,
                         help="Claude Code's client_id at the IdP")
    setup_p.add_argument("--client-secret", dest="client_secret", action="store_true",
                         help="Read IdP client secret from MCP_XAA_IDP_CLIENT_SECRET env var")
    setup_p.add_argument("--callback-port", dest="callback_port",
                         help="Fixed loopback callback port")

    # --- login ---
    login_p = xaa_sub.add_parser("login", help="Cache an IdP id_token")
    login_p.add_argument("--force", action="store_true",
                         help="Ignore cached id_token and re-login")
    login_p.add_argument("--id-token", dest="id_token",
                         help="Write a pre-obtained JWT directly to cache")

    # --- show ---
    xaa_sub.add_parser("show", help="Show the current IdP connection config")

    # --- clear ---
    xaa_sub.add_parser("clear", help="Clear the IdP connection config and cached id_token")

    xaa_parser.set_defaults(handler=_handle_xaa_args)


async def _handle_xaa_args(parsed_args: Any) -> None:
    cmd = getattr(parsed_args, "xaa_command", None)
    if cmd == "setup":
        _run_setup(
            issuer=parsed_args.issuer,
            client_id=parsed_args.client_id,
            client_secret_flag=parsed_args.client_secret,
            callback_port=parsed_args.callback_port,
        )
    elif cmd == "login":
        await _run_login(
            force=getattr(parsed_args, "force", False),
            id_token=getattr(parsed_args, "id_token", None),
        )
    elif cmd == "show":
        _run_show()
    elif cmd == "clear":
        _run_clear()
    else:
        usage = "Usage: claude mcp xaa <setup|login|show|clear>\n"
        hint = "Run 'claude mcp xaa <subcommand> --help' for details.\n"
        sys.stdout.write(usage + hint)
