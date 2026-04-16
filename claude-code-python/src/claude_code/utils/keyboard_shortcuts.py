"""
Keyboard shortcut constants.
Port of utils/keyboardShortcuts.ts
"""

# Special characters that macOS Option+key produces, mapped to their
# keybinding equivalents. Used to detect Option+key shortcuts on macOS
# terminals that don't have "Option as Meta" enabled.
MACOS_OPTION_SPECIAL_CHARS: dict[str, str] = {
    "†": "alt+t",  # Option+T -> thinking toggle
    "π": "alt+p",  # Option+P -> model picker
    "ø": "alt+o",  # Option+O -> fast mode
}


def is_macos_option_char(char: str) -> bool:
    """Return True if char is a macOS Option+key special character."""
    return char in MACOS_OPTION_SPECIAL_CHARS
