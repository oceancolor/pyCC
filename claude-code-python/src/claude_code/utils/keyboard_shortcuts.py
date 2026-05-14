"""Keyboard shortcut helpers. Ported from keyboardShortcuts.ts.

Maps macOS Option+key special characters to their keybinding equivalents
and provides helpers for detecting keyboard shortcuts in terminal input.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

__all__ = [
    "MACOS_OPTION_SPECIAL_CHARS",
    "is_macos_option_char",
    "get_keybinding_for_option_char",
    "parse_key_sequence",
    "format_shortcut",
    "KeyBinding",
]

# Special characters that macOS Option+key produces, mapped to their
# keybinding equivalents.  Used to detect Option+key shortcuts on macOS
# terminals that do not have "Option as Meta" enabled.
MACOS_OPTION_SPECIAL_CHARS: Dict[str, str] = {
    "\u2020": "alt+t",   # Option+T → thinking toggle  (†)
    "\u03c0": "alt+p",   # Option+P → model picker     (π)
    "\u00f8": "alt+o",   # Option+O → fast mode        (ø)
    "\u221e": "alt+5",   # Option+5 → (∞)
    "\u2022": "alt+8",   # Option+8 → (•)
}

# Map modifier key names to their display representations
_MODIFIER_DISPLAY: Dict[str, str] = {
    "ctrl": "^",
    "alt": "⌥",
    "meta": "⌘",
    "shift": "⇧",
}


class KeyBinding:
    """Represents a keyboard shortcut with modifiers and a key."""

    def __init__(self, key: str, ctrl: bool = False, alt: bool = False, meta: bool = False, shift: bool = False) -> None:
        self.key = key
        self.ctrl = ctrl
        self.alt = alt
        self.meta = meta
        self.shift = shift

    def __repr__(self) -> str:
        return f"KeyBinding({format_shortcut(self)})"

    def matches(self, other: "KeyBinding") -> bool:
        return (
            self.key == other.key
            and self.ctrl == other.ctrl
            and self.alt == other.alt
            and self.meta == other.meta
            and self.shift == other.shift
        )


def is_macos_option_char(char: str) -> bool:
    """Return True if *char* is a macOS Option+key special character."""
    return char in MACOS_OPTION_SPECIAL_CHARS


def get_keybinding_for_option_char(char: str) -> Optional[str]:
    """Return the keybinding string for a macOS Option+key char, or None."""
    return MACOS_OPTION_SPECIAL_CHARS.get(char)


def parse_key_sequence(sequence: str) -> Optional[KeyBinding]:
    """Parse a keybinding string like 'ctrl+k', 'alt+t', 'shift+enter'.

    Returns a KeyBinding or None if *sequence* cannot be parsed.
    """
    parts = [p.lower().strip() for p in sequence.split("+")]
    if not parts:
        return None
    key = parts[-1]
    modifiers = set(parts[:-1])
    return KeyBinding(
        key=key,
        ctrl="ctrl" in modifiers or "control" in modifiers,
        alt="alt" in modifiers or "option" in modifiers,
        meta="meta" in modifiers or "cmd" in modifiers or "command" in modifiers,
        shift="shift" in modifiers,
    )


def format_shortcut(binding: KeyBinding) -> str:
    """Return a human-readable representation of *binding*."""
    parts: List[str] = []
    if binding.ctrl:
        parts.append(_MODIFIER_DISPLAY.get("ctrl", "Ctrl+"))
    if binding.alt:
        parts.append(_MODIFIER_DISPLAY.get("alt", "Alt+"))
    if binding.meta:
        parts.append(_MODIFIER_DISPLAY.get("meta", "⌘"))
    if binding.shift:
        parts.append(_MODIFIER_DISPLAY.get("shift", "⇧"))
    parts.append(binding.key.upper())
    return "".join(parts)
