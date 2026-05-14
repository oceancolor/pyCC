"""GitHub utilities sub-package. Ported from utils/github/.

Provides helpers for interacting with the gh CLI and GitHub APIs.
"""
from __future__ import annotations

from claude_code.utils.github.gh_auth_status import (
    GhAuthStatus,
    get_gh_auth_status,
)

__all__ = [
    "GhAuthStatus",
    "get_gh_auth_status",
]
