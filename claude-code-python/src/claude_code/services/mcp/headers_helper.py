"""
MCP server headers helper utilities.
Ported from services/mcp/headersHelper.ts

Provides static and dynamic header resolution for MCP HTTP/SSE/WebSocket servers.
Dynamic headers are obtained by executing a configured headersHelper script (git-credential-helper style).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from typing import Dict, Optional

log = logging.getLogger(__name__)


def _is_mcp_server_from_project_or_local_settings(config: dict) -> bool:
    """Return True if the config comes from project or local settings scope."""
    return config.get("scope") in ("project", "local")


def _get_is_non_interactive_session() -> bool:
    """Check if running in non-interactive session (CI/CD, automation)."""
    try:
        from claude_code.bootstrap.state import get_is_non_interactive_session  # type: ignore
        return get_is_non_interactive_session()
    except ImportError:
        return bool(os.environ.get("CLAUDE_CODE_NON_INTERACTIVE"))


def _check_has_trust_dialog_accepted() -> bool:
    """Check if workspace trust has been established."""
    try:
        from claude_code.utils.config import check_has_trust_dialog_accepted  # type: ignore
        return check_has_trust_dialog_accepted()
    except ImportError:
        return True  # Default to trusted when check unavailable


async def get_mcp_headers_from_helper(
    server_name: str,
    config: dict,
) -> Optional[Dict[str, str]]:
    """Get dynamic headers for an MCP server using the headersHelper script.

    Mirrors ``getMcpHeadersFromHelper`` from the TypeScript source.

    Args:
        server_name: The name of the MCP server.
        config: The MCP server configuration dict.

    Returns:
        Headers dict or None if not configured or failed.
    """
    headers_helper = config.get("headersHelper")
    if not headers_helper:
        return None

    # Security check for project/local settings (skip in non-interactive mode)
    if (
        _is_mcp_server_from_project_or_local_settings(config)
        and not _get_is_non_interactive_session()
    ):
        has_trust = _check_has_trust_dialog_accepted()
        if not has_trust:
            log.error(
                "Security: headersHelper for MCP server '%s' invoked before workspace trust is confirmed.",
                server_name,
            )
            return None

    try:
        log.debug("Executing headersHelper for MCP server '%s'", server_name)
        env = {
            **os.environ,
            "CLAUDE_CODE_MCP_SERVER_NAME": server_name,
            "CLAUDE_CODE_MCP_SERVER_URL": config.get("url", ""),
        }
        proc = await asyncio.create_subprocess_shell(
            headers_helper,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=10.0
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(
                f"headersHelper for MCP server '{server_name}' timed out after 10s"
            )

        if proc.returncode != 0 or not stdout:
            raise RuntimeError(
                f"headersHelper for MCP server '{server_name}' did not return a valid value"
            )

        result = stdout.decode().strip()
        headers = json.loads(result)

        if not isinstance(headers, dict) or isinstance(headers, list):
            raise RuntimeError(
                f"headersHelper for MCP server '{server_name}' must return a JSON object"
            )

        # Validate all values are strings
        for key, value in headers.items():
            if not isinstance(value, str):
                raise RuntimeError(
                    f"headersHelper for MCP server '{server_name}' returned non-string value for key '{key}'"
                )

        log.debug(
            "Retrieved %d headers from headersHelper for '%s'",
            len(headers),
            server_name,
        )
        return headers  # type: ignore[return-value]

    except Exception as exc:
        log.error(
            "Error getting MCP headers from headersHelper for server '%s': %s",
            server_name,
            exc,
        )
        return None


async def get_mcp_server_headers(
    server_name: str,
    config: dict,
) -> Dict[str, str]:
    """Get combined headers for an MCP server (static + dynamic).

    Dynamic headers override static headers if both are present.
    Mirrors ``getMcpServerHeaders`` from the TypeScript source.

    Args:
        server_name: The name of the MCP server.
        config: The MCP server configuration dict.

    Returns:
        Combined headers dict (never None).
    """
    static_headers: Dict[str, str] = config.get("headers") or {}
    dynamic_headers: Dict[str, str] = (
        await get_mcp_headers_from_helper(server_name, config)
    ) or {}

    return {**static_headers, **dynamic_headers}
