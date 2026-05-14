"""Worktree mode feature gate. Ported from utils/worktreeModeEnabled.ts

Worktree mode is unconditionally enabled for all users.
The prior GrowthBook gate was removed because the CACHED_MAY_BE_STALE
pattern returned the default (false) on first launch before the cache
was populated, silently swallowing --worktree.
See https://github.com/anthropics/claude-code/issues/27044.
"""

from __future__ import annotations

import os


def is_worktree_mode_enabled() -> bool:
    """Return True — worktree mode is unconditionally enabled.

    Originally gated by GrowthBook flag ``tengu_worktree_mode`` but now
    always returns True. The environment variable
    ``CLAUDE_CODE_WORKTREE_MODE_DISABLED=1`` can be used in tests to
    override this behaviour.
    """
    if os.environ.get("CLAUDE_CODE_WORKTREE_MODE_DISABLED") == "1":
        return False
    return True


def assert_worktree_mode_enabled() -> None:
    """Raise :exc:`RuntimeError` if worktree mode is not enabled.

    Convenience helper for code paths that require worktree mode.
    """
    if not is_worktree_mode_enabled():
        raise RuntimeError(
            "Worktree mode is not enabled. "
            "Unset CLAUDE_CODE_WORKTREE_MODE_DISABLED to enable it."
        )
