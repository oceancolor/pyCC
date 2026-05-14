"""Computer use utilities sub-package. Ported from utils/computerUse/.

Provides helpers for the computer use (screen control) feature including
capability gating, MCP server setup, and platform-specific executors.
"""
from __future__ import annotations

from claude_code.utils.computer_use.common import (
    get_terminal_bundle_id,
    is_computer_use_mcp_server,
)
from claude_code.utils.computer_use.gates import (
    get_chicago_enabled,
)

__all__ = [
    "get_terminal_bundle_id",
    "is_computer_use_mcp_server",
    "get_chicago_enabled",
]
