"""Compact warning hook. Ported from services/compact/compactWarningHook.ts

The TS version is a React hook; here we expose a plain function.
"""
from __future__ import annotations
from claude_code.services.compact.compact_warning_state import get_compact_warning_state


def use_compact_warning_suppression() -> bool:
    """Return current compact warning suppression state.

    In Python we return a plain bool rather than a React reactive value.
    """
    return get_compact_warning_state()


def should_show_compact_warning() -> bool:
    """Return True if the compact warning should be displayed."""
    return not get_compact_warning_state()
