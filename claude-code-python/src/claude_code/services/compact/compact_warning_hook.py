"""Compact warning hook. Ported from services/compact/compactWarningHook.ts

The TS version is a React hook; here we expose a plain function.
"""
from __future__ import annotations
from claude_code.services.compact.compact_warning_state import compact_warning_store


def use_compact_warning_suppression() -> bool:
    """Return current compact warning suppression state.

    In Python we return a plain bool rather than a React reactive value.
    Check compact_warning_store.get_state() to react to changes.
    """
    return compact_warning_store.get_state()
