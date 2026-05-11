"""macOS keyboard shortcut helpers. Ported from utils/keyboardShortcuts.ts"""
from __future__ import annotations
from typing import Optional

# Special characters that macOS Option+key produces, mapped to their
# keybinding equivalents.  Used to detect Option+key shortcuts on macOS
# terminals that do not have "Option as Meta" enabled.
MACOS_OPTION_SPECIAL_CHARS: dict[str, str] = {
    "\u2020": "alt+t",  # Option+T → thinking toggle  (†)
    "\u03c0": "alt+p",  # Option+P → model picker     (π)
    "\u00f8": "alt+o",  # Option+O → fast mode        (ø)
}


def is_macos_option_char(char: str) -> bool:
    """Return True if *char* is a macOS Option+key special character."""
    return char in MACOS_OPTION_SPECIAL_CHARS


def get_keybinding_for_option_char(char: str) -> Optional[str]:
    """Return the keybinding string for a macOS Option+key character, or None."""
    return MACOS_OPTION_SPECIAL_CHARS.get(char)
