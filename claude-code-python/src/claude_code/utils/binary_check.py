"""Binary / executable detection. Ported from binaryCheck.ts.

Checks for the presence of system executables (git, node, ripgrep, …) that
Claude Code depends on at runtime.  Results are cached after the first lookup
to avoid repeated shutil.which() calls in hot paths.
"""
from __future__ import annotations

import shutil
from typing import Dict, List, Optional, Tuple

__all__ = [
    "find_binary",
    "is_available",
    "require_binary",
    "check_binaries",
    "clear_binary_cache",
    "REQUIRED_BINARIES",
    "OPTIONAL_BINARIES",
]

# List of binaries that Claude Code requires to function
REQUIRED_BINARIES: Tuple[str, ...] = ("git",)

# List of binaries that improve Claude Code but are not required
OPTIONAL_BINARIES: Tuple[str, ...] = (
    "rg",          # ripgrep – fast file search
    "node",        # Node.js – needed for JS tool execution
    "npm",         # npm – Node package manager
    "gh",          # GitHub CLI
    "fd",          # fd – fast file find (optional alternative to find)
)

# Cache of binary → resolved path (None if not found)
_cache: Dict[str, Optional[str]] = {}


def find_binary(name: str) -> Optional[str]:
    """Return the absolute path to *name* if found on PATH, else None.

    Results are cached; call clear_binary_cache() to invalidate.
    """
    if name not in _cache:
        _cache[name] = shutil.which(name)
    return _cache[name]


def is_available(name: str) -> bool:
    """Return True if *name* is executable on the current PATH."""
    return find_binary(name) is not None


def require_binary(name: str) -> str:
    """Return the path to *name*, raising FileNotFoundError if absent."""
    path = find_binary(name)
    if path is None:
        raise FileNotFoundError(
            f"Required binary not found on PATH: {name!r}. "
            "Please install it and try again."
        )
    return path


def check_binaries(*names: str) -> Dict[str, bool]:
    """Return a mapping of binary name → availability for each name in *names*."""
    return {name: is_available(name) for name in names}


def clear_binary_cache() -> None:
    """Invalidate all cached binary lookups (useful in tests)."""
    _cache.clear()


def get_missing_required() -> List[str]:
    """Return a list of required binaries that are not available."""
    return [name for name in REQUIRED_BINARIES if not is_available(name)]


def get_available_optional() -> List[str]:
    """Return a list of optional binaries that ARE available."""
    return [name for name in OPTIONAL_BINARIES if is_available(name)]
