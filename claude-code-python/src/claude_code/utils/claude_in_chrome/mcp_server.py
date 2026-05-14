"""MCP server for claude-in-chrome feature. Ported from utils/claudeInChrome/mcpServer.ts"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

EXTENSION_DOWNLOAD_URL = "https://claude.ai/chrome"
BUG_REPORT_URL = (
    "https://github.com/anthropics/claude-code/issues/new?labels=bug,claude-in-chrome"
)

# Permission modes supported by the chrome bridge
PERMISSION_MODES = ("ask", "skip_all_permission_checks", "follow_a_plan")


def is_permission_mode(raw: str) -> bool:
    """Return True if ``raw`` is a valid permission mode string."""
    return raw in PERMISSION_MODES


def get_chrome_bridge_url() -> Optional[str]:
    """Resolve the Chrome bridge URL based on environment and feature flags.

    Returns None when the bridge is not enabled (fall back to native messaging).
    """
    user_type = os.environ.get("USER_TYPE")
    bridge_enabled = user_type == "ant" or os.environ.get("TENGU_COPPER_BRIDGE") == "1"

    if not bridge_enabled:
        return None

    env_url = os.environ.get("CLAUDE_IN_CHROME_BRIDGE_URL")
    if env_url:
        return env_url

    base = os.environ.get("CLAUDE_API_BASE_URL", "https://api.claude.ai")
    return f"{base}/api/claude-in-chrome/bridge"


async def run_mcp_server(
    session_id: str,
    permission_mode: str = "ask",
    on_ready: Optional[Callable[[], None]] = None,
) -> None:
    """Run the claude-in-chrome MCP server for the given session.

    This is the Python-port stub of the MCP server entry point. The actual
    MCP server logic lives in the ``@ant/claude-for-chrome-mcp`` npm package
    in the TypeScript implementation; here we provide a minimal Python shim
    that exposes the same interface.

    Args:
        session_id: Unique session identifier (used to locate the socket).
        permission_mode: One of ``PERMISSION_MODES``.
        on_ready: Optional callback invoked when the server is ready to accept connections.
    """
    from .common import get_secure_socket_path, get_socket_dir

    if not is_permission_mode(permission_mode):
        raise ValueError(f"Unknown permission mode: {permission_mode!r}")

    socket_path = get_secure_socket_path(session_id)
    socket_dir = get_socket_dir()
    os.makedirs(socket_dir, mode=0o700, exist_ok=True)

    log.info("Starting claude-in-chrome MCP server (session=%s)", session_id)

    if on_ready:
        on_ready()

    # In the full TypeScript implementation this runs an MCP stdio server loop.
    # The Python port defers to the MCP SDK when available.
    try:
        from mcp.server import Server  # type: ignore[import]
        from mcp.server.stdio import stdio_server  # type: ignore[import]

        server = Server("claude-in-chrome")
        # Tool handlers would be registered here in a full implementation
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    except ImportError:
        log.warning(
            "MCP Python SDK not installed; claude-in-chrome MCP server unavailable. "
            "Install with: pip install mcp"
        )
        # Hold until cancelled
        await asyncio.Event().wait()
