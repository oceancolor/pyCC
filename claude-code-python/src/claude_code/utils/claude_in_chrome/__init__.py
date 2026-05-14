"""Claude-in-Chrome utilities sub-package. Ported from utils/claudeInChrome/.

Provides helpers for the Claude browser extension integration including
native host messaging, MCP server setup, and Chrome extension communication.
"""
from __future__ import annotations

from claude_code.utils.claude_in_chrome.common import (
    get_secure_socket_path,
    get_socket_dir,
)
from claude_code.utils.claude_in_chrome.setup_portable import (
    get_extension_install_instructions,
    get_supported_browsers,
)

__all__ = [
    "get_socket_dir",
    "get_secure_socket_path",
    "get_supported_browsers",
    "get_extension_install_instructions",
]
