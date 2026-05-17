"""
State management package.
Ported from: src/state/ (TypeScript)

Provides the core application and session state types used throughout
the Claude Code codebase.

  - SessionState  — per-session runtime state (messages, tokens, etc.)

The full AppState (tasks, MCP clients, tools, etc.) is defined in
``claude_code.state.app_state`` and loaded lazily to keep import time small.
"""
from __future__ import annotations

from claude_code.state.session_state import SessionState

__all__ = [
    "SessionState",
]
