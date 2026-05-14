"""
Claude Code Python Port

This package provides the Python port of Anthropic's Claude Code CLI tool.
"""
from __future__ import annotations

from claude_code._version import __version__

__all__ = [
    "__version__",
]

# Lazy exports — use explicit imports in production code for faster startup
def _get_version() -> str:
    return __version__
