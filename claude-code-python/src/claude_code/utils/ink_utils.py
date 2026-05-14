"""Ink / terminal color utilities. Ported from ink.ts / inkUtils.ts.

In the TypeScript source Ink is a React-for-CLIs library with its own color
system.  In Python we map Ink color names to ANSI escape codes so the rest of
the codebase can reference Ink color names without pulling in a full TUI stack.
"""
from __future__ import annotations

from typing import Optional

__all__ = [
    "DEFAULT_AGENT_THEME_COLOR",
    "to_ink_color",
    "ink_color_to_ansi",
    "strip_ansi",
    "colorize",
]

DEFAULT_AGENT_THEME_COLOR = "cyan"

# Map Ink/CSS color names → ANSI escape codes (foreground)
_ANSI_COLORS: dict[str, str] = {
    "black": "\x1b[30m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
    "white": "\x1b[37m",
    "gray": "\x1b[90m",
    "grey": "\x1b[90m",
    "bright_red": "\x1b[91m",
    "bright_green": "\x1b[92m",
    "bright_yellow": "\x1b[93m",
    "bright_blue": "\x1b[94m",
    "bright_magenta": "\x1b[95m",
    "bright_cyan": "\x1b[96m",
    "bright_white": "\x1b[97m",
}

_ANSI_RESET = "\x1b[0m"

# Ink-specific aliases that differ from standard ANSI names
_INK_ALIASES: dict[str, str] = {
    "greenBright": "bright_green",
    "redBright": "bright_red",
    "yellowBright": "bright_yellow",
    "blueBright": "bright_blue",
    "magentaBright": "bright_magenta",
    "cyanBright": "bright_cyan",
    "whiteBright": "bright_white",
}


def to_ink_color(color: Optional[str]) -> str:
    """Normalise *color* to an Ink-compatible color name.

    Falls back to DEFAULT_AGENT_THEME_COLOR if *color* is None or unknown.
    """
    if not color:
        return DEFAULT_AGENT_THEME_COLOR
    lower = color.lower()
    resolved = _INK_ALIASES.get(color) or _INK_ALIASES.get(lower) or lower
    if resolved in _ANSI_COLORS:
        return resolved
    # Unknown color – return as-is so callers can pass hex values (#ff0000)
    return color


def ink_color_to_ansi(color: Optional[str]) -> str:
    """Convert an Ink/ANSI color name to an ANSI escape sequence.

    Returns empty string if the color name is unrecognised (e.g., hex colors).
    """
    resolved = to_ink_color(color)
    return _ANSI_COLORS.get(resolved, "")


def colorize(text: str, color: Optional[str]) -> str:
    """Wrap *text* with ANSI color codes for *color*.

    Returns *text* unchanged if the color is unknown or None.
    """
    esc = ink_color_to_ansi(color)
    if not esc:
        return text
    return f"{esc}{text}{_ANSI_RESET}"


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    import re

    return re.sub(r"\x1b\[[0-9;]*[mGKHF]", "", text)
