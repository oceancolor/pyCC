"""Compact warning hook. Ported from services/compact/compactWarningHook.ts"""
from claude_code.services.compact.compact_warning_state import get_compact_warning_shown

def should_show_compact_warning() -> bool:
    return not get_compact_warning_shown()
