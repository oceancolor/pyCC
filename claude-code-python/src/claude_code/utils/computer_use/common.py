"""
common.py - Common constants and utilities for computer use.

Port of TypeScript common.ts.
"""

import os
from typing import Optional


COMPUTER_USE_MCP_SERVER_NAME = 'computer-use'

# Sentinel bundle ID for the frontmost gate
CLI_HOST_BUNDLE_ID = 'com.anthropic.claude-code.cli-no-window'

# Fallback terminal → bundleId map
_TERMINAL_BUNDLE_ID_FALLBACK = {
    'iTerm.app': 'com.googlecode.iterm2',
    'Apple_Terminal': 'com.apple.Terminal',
    'ghostty': 'com.mitchellh.ghostty',
    'kitty': 'net.kovidgoyal.kitty',
    'WarpTerminal': 'dev.warp.Warp-Stable',
    'vscode': 'com.microsoft.VSCode',
}

# Static capabilities for macOS CLI
CLI_CU_CAPABILITIES = {
    'screenshotFiltering': 'native',
    'platform': 'darwin',
}


def get_terminal_bundle_id() -> Optional[str]:
    """
    Returns the bundle ID of the terminal emulator we're running inside.

    Returns:
        Bundle ID string or None if undetectable.
    """
    cf_bundle_id = os.environ.get('__CFBundleIdentifier')
    if cf_bundle_id:
        return cf_bundle_id

    terminal = os.environ.get('TERM_PROGRAM') or os.environ.get('TERMINAL_EMULATOR', '')
    return _TERMINAL_BUNDLE_ID_FALLBACK.get(terminal)


def is_computer_use_mcp_server(name: str) -> bool:
    """Check if the given server name is the computer-use MCP server."""
    from ...services.mcp.normalization import normalize_name_for_mcp
    return normalize_name_for_mcp(name) == COMPUTER_USE_MCP_SERVER_NAME
