"""Compact warning hook.

Ported from: src/services/compact/compactWarningHook.ts

The TypeScript original is a React hook (``useCompactWarningSuppression``)
that tracks whether the compact-warning banner should be suppressed.
In the Python port this is a plain module-level function because there is
no React state.

Usage::

    from claude_code.services.compact.compact_warning_hook import (
        use_compact_warning_suppression,
        should_show_compact_warning,
    )
"""
from __future__ import annotations

from claude_code.services.compact.compact_warning_state import get_compact_warning_state


def use_compact_warning_suppression() -> bool:
    """Return the current compact-warning suppression state.

    When ``True`` the compact-warning banner is suppressed.

    In the Python port this returns a plain ``bool`` rather than a
    reactive React state value.
    """
    return get_compact_warning_state()


def should_show_compact_warning() -> bool:
    """Return ``True`` when the compact-warning banner should be displayed."""
    return not get_compact_warning_state()


__all__ = [
    "use_compact_warning_suppression",
    "should_show_compact_warning",
]
