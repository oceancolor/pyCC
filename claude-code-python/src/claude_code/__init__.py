"""
Claude Code Python Port

Top-level package. Provides the version and lazy access to core subsystems.
Ported from the TypeScript source (main entry points).
"""
from __future__ import annotations

from claude_code._version import __version__


def get_version() -> str:
    """Return the package version string."""
    return __version__


__all__ = [
    "__version__",
    "get_version",
]
