"""State management package.

Provides the core application and session state types used throughout
Claude Code.

Ported from: src/state/ (TypeScript)

Sub-modules
-----------
session_state
    Per-session runtime state (messages, token counts, active tools, etc.).
app_state
    Full application state including tasks, MCP clients, and global config.
    Loaded lazily to keep import time small.

Usage::

    from claude_code.state import SessionState
"""
from __future__ import annotations

from claude_code.state.session_state import SessionState

__all__ = [
    "SessionState",
]
