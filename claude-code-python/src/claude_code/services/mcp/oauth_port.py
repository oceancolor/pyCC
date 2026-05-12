"""
OAuth redirect port helpers for MCP authentication.
Ported from services/mcp/oauthPort.ts

Extracted to break circular dependency between auth.ts and xaaIdpLogin.ts.
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
from typing import Optional

# Windows dynamic port range 49152-65535 is reserved; use a lower range on Windows
if sys.platform == "win32":
    _REDIRECT_PORT_RANGE = (39152, 49151)
else:
    _REDIRECT_PORT_RANGE = (49152, 65535)

REDIRECT_PORT_FALLBACK = 3118


def build_redirect_uri(port: int = REDIRECT_PORT_FALLBACK) -> str:
    """Build a redirect URI on localhost with a fixed /callback path.

    RFC 8252 Section 7.3 (OAuth for Native Apps): loopback redirect URIs
    match any port as long as the path matches.
    """
    return f"http://localhost:{port}/callback"


def _get_mcp_oauth_callback_port() -> Optional[int]:
    raw = os.environ.get("MCP_OAUTH_CALLBACK_PORT", "")
    try:
        port = int(raw)
        return port if port > 0 else None
    except ValueError:
        return None


async def _is_port_available(port: int) -> bool:
    """Return True if the given TCP port can be bound on localhost."""
    try:
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", port)
        server.close()
        await server.wait_closed()
        return True
    except OSError:
        return False


async def find_available_port() -> int:
    """Find an available port for OAuth redirect.

    First tries the configured port (MCP_OAUTH_CALLBACK_PORT), then random
    ports in the platform-appropriate range, then falls back to the default.

    Returns:
        An available TCP port number.

    Raises:
        RuntimeError: If no available port can be found.
    """
    # Try configured port first
    configured = _get_mcp_oauth_callback_port()
    if configured:
        return configured

    min_port, max_port = _REDIRECT_PORT_RANGE
    port_range = max_port - min_port + 1
    max_attempts = min(port_range, 100)

    for _ in range(max_attempts):
        port = min_port + random.randint(0, port_range - 1)
        if await _is_port_available(port):
            return port

    # Fallback port
    if await _is_port_available(REDIRECT_PORT_FALLBACK):
        return REDIRECT_PORT_FALLBACK

    raise RuntimeError("No available ports for OAuth redirect")
