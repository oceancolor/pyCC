"""Version information for the claude-code Python port.

Ported from the original TypeScript Claude Code project.

This module is the single source of truth for the package version.
It is imported by ``setup.cfg``/``pyproject.toml`` (via ``importlib.metadata``)
and is also available at runtime for version checks and display.
"""
from __future__ import annotations

#: Semantic version string following SemVer (MAJOR.MINOR.PATCH).
__version__: str = "1.0.0"

#: Alias for ``__version__``.  Matches the convention used by many
#: packaging tools (e.g. ``pkg.__version__`` and ``pkg.VERSION``).
VERSION: str = __version__

#: Version as a (major, minor, patch) integer tuple for programmatic
#: comparisons (e.g. ``if VERSION_TUPLE >= (1, 2, 0): ...``).
VERSION_TUPLE: tuple[int, int, int] = (1, 0, 0)

__all__ = ["__version__", "VERSION", "VERSION_TUPLE"]
