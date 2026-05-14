"""State management package for Claude Code.

Provides the core application and session state types used throughout
the Claude Code codebase. Ported from the TypeScript state/ module.
"""
from __future__ import annotations

from claude_code.state.session_state import SessionState

__all__ = [
    "SessionState",
]
