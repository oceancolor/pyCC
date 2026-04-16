"""Compact warning state. Ported from services/compact/compactWarningState.ts"""
from __future__ import annotations
_compact_warning_shown = False

def get_compact_warning_shown() -> bool:
    return _compact_warning_shown

def set_compact_warning_shown(v: bool) -> None:
    global _compact_warning_shown
    _compact_warning_shown = v
