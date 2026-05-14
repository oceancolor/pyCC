"""Modifier key detection (macOS only). Ported from modifiers.ts.

Pre-warms the native module by loading it in advance and provides a
synchronous check for whether a specific modifier key is currently pressed.
Non-macOS platforms always return False.
"""
from __future__ import annotations

import sys
from typing import Literal, Optional

__all__ = [
    "ModifierKey",
    "prewarm_modifiers",
    "is_modifier_pressed",
    "get_pressed_modifiers",
    "is_any_modifier_pressed",
]

ModifierKey = Literal["shift", "command", "control", "option"]

_PREWARMED = False


def prewarm_modifiers() -> None:
    """Pre-warm the native modifier module by loading it in advance.

    Call this early (e.g., on startup) to avoid a delay on first use.
    Safe to call multiple times (idempotent).  No-op on non-macOS platforms.
    """
    global _PREWARMED
    if _PREWARMED or sys.platform != "darwin":
        return
    _PREWARMED = True
    try:
        import modifiers_napi  # type: ignore[import]

        # Trigger the module's own pre-warm if available
        if hasattr(modifiers_napi, "prewarm"):
            modifiers_napi.prewarm()
    except Exception:
        pass


def is_modifier_pressed(modifier: ModifierKey) -> bool:
    """Return True if the specified modifier key is currently held down.

    Always returns False on non-macOS platforms or when the native
    ``modifiers_napi`` extension is not installed.
    """
    if sys.platform != "darwin":
        return False
    try:
        import modifiers_napi  # type: ignore[import]

        return bool(modifiers_napi.is_modifier_pressed(modifier))
    except Exception:
        return False


def get_pressed_modifiers() -> list[ModifierKey]:
    """Return a list of modifier keys that are currently pressed.

    Returns an empty list on non-macOS platforms or if the native module
    is unavailable.
    """
    all_keys: list[ModifierKey] = ["shift", "command", "control", "option"]
    return [k for k in all_keys if is_modifier_pressed(k)]


def is_any_modifier_pressed() -> bool:
    """Return True if any modifier key is currently pressed."""
    return any(is_modifier_pressed(k) for k in ("shift", "command", "control", "option"))
