"""
Modifier key detection (macOS only). Ported from modifiers.ts
"""
from __future__ import annotations
import sys
from typing import Literal

ModifierKey = Literal["shift", "command", "control", "option"]


def prewarm_modifiers() -> None:
    """No-op on non-macOS platforms."""
    pass


def is_modifier_pressed(modifier: ModifierKey) -> bool:
    """Always returns False on non-macOS or when native module unavailable."""
    if sys.platform != "darwin":
        return False
    try:
        import modifiers_napi  # type: ignore
        return modifiers_napi.is_modifier_pressed(modifier)
    except ImportError:
        return False
