"""
Git availability - checks if git is available on the system.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Optional

_git_available: Optional[bool] = None
_git_version: Optional[str] = None


def is_git_available() -> bool:
    """Check if git is available on the system."""
    global _git_available
    if _git_available is None:
        _git_available = shutil.which("git") is not None
    return _git_available


def get_git_version() -> Optional[str]:
    """Get the git version string, or None if git is unavailable."""
    global _git_version
    if _git_version is not None:
        return _git_version
    if not is_git_available():
        return None
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            _git_version = result.stdout.strip()
            return _git_version
    except Exception:
        pass
    return None


def reset_git_availability_cache() -> None:
    """Reset the git availability cache (for testing)."""
    global _git_available, _git_version
    _git_available = None
    _git_version = None
