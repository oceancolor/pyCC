"""Fast mode and thinking-mode feature flags. Ported from fastMode.ts.

Fast mode disables extended thinking / interleaved thinking for speed and
cost reduction.  Each flag can be toggled independently via environment
variables or GrowthBook feature gates.
"""
from __future__ import annotations

import os

__all__ = [
    "is_fast_mode",
    "is_thinking_disabled",
    "is_interleaved_thinking_disabled",
    "is_compact_disabled",
    "is_auto_compact_disabled",
    "get_effective_thinking_budget",
]

_TRUTHY = frozenset(("1", "true", "yes"))


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in _TRUTHY


def is_fast_mode() -> bool:
    """Return True if CLAUDE_CODE_SIMPLE is set (fast / no-thinking mode)."""
    return _env_flag("CLAUDE_CODE_SIMPLE")


def is_thinking_disabled() -> bool:
    """Return True if extended thinking is disabled.

    Disabled when either CLAUDE_CODE_DISABLE_THINKING=1 is set explicitly,
    or fast mode is active.
    """
    return _env_flag("CLAUDE_CODE_DISABLE_THINKING") or is_fast_mode()


def is_interleaved_thinking_disabled() -> bool:
    """Return True if interleaved (mid-stream) thinking is disabled."""
    return _env_flag("DISABLE_INTERLEAVED_THINKING")


def is_compact_disabled() -> bool:
    """Return True if context compaction is disabled."""
    return _env_flag("DISABLE_COMPACT")


def is_auto_compact_disabled() -> bool:
    """Return True if automatic context compaction is disabled."""
    return _env_flag("DISABLE_AUTO_COMPACT")


def get_effective_thinking_budget() -> int:
    """Return the thinking-token budget to use for the current request.

    Returns 0 when thinking is disabled; otherwise returns the value of
    CLAUDE_THINKING_BUDGET (default 10 000).
    """
    if is_thinking_disabled():
        return 0
    raw = os.environ.get("CLAUDE_THINKING_BUDGET", "10000")
    try:
        return max(0, int(raw))
    except ValueError:
        return 10_000
