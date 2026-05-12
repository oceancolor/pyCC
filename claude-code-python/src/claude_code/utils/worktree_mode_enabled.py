"""
Worktree mode feature gate.
Ported from utils/worktreeModeEnabled.ts

Worktree mode is unconditionally enabled for all users.
The prior GrowthBook gate was removed because the CACHED_MAY_BE_STALE
pattern returned the default (false) on first launch before the cache
was populated, silently swallowing --worktree.
"""
from __future__ import annotations


def is_worktree_mode_enabled() -> bool:
    """Return True — worktree mode is unconditionally enabled."""
    return True
