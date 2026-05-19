"""GitHub utilities.

Provides helpers for interacting with the ``gh`` CLI and the GitHub REST
API, including authentication status checks and repository metadata
lookups.

Ported from: src/utils/github/ (TypeScript)

Usage::

    from claude_code.utils.github import GhAuthStatus, get_gh_auth_status
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
