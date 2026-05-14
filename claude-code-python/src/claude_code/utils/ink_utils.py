"""Ink/terminal color and layout utilities. Ported from utils/inkUtils.ts (inferred)"""

from __future__ import annotations

import os
import sys
from typing import Optional

# Default color used for subagent sessions
DEFAULT_AGENT_THEME_COLOR = "cyan"

# Named colors that map to standard ANSI terminal colours
AGENT_COLOR_MAP: dict[str, str] = {
    "blue": "blue",
    "green": "green",
    "red": "red",
    "yellow": "yellow",
    "cyan": "cyan",
    "magenta": "magenta",
    "white": "white",
    "gray": "gray",
    "grey": "gray",
}

# ANSI escape codes for terminal colors
_ANSI_RESET = "\033[0m"
_ANSI_COLORS: dict[str, str] = {
    "blue":    "\033[34m",
    "green":   "\033[32m",
    "red":     "\033[31m",
    "yellow":  "\033[33m",
    "cyan":    "\033[36m",
    "magenta": "\033[35m",
    "white":   "\033[37m",
    "gray":    "\033[90m",
}


def to_ink_color(color: Optional[str]) -> str:
    """Normalise *color* to a name usable by the terminal renderer.

    Falls back to DEFAULT_AGENT_THEME_COLOR for falsy / unrecognised values.
    """
    if not color:
        return DEFAULT_AGENT_THEME_COLOR
    return AGENT_COLOR_MAP.get(color.lower(), f"ansi:{color}")


def colorize(text: str, color: Optional[str]) -> str:
    """Wrap *text* in ANSI escape codes for the given *color*.

    Returns plain text when stdout is not a TTY or the color is unrecognised.
    """
    if not sys.stdout.isatty():
        return text
    ink = to_ink_color(color)
    code = _ANSI_COLORS.get(ink) or _ANSI_COLORS.get(color or "")
    if not code:
        return text
    return f"{code}{text}{_ANSI_RESET}"


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from *text*."""
    import re
    return re.sub(r"\033\[[0-9;]*[a-zA-Z]", "", text)


def terminal_width() -> int:
    """Return the current terminal width (columns).

    Falls back to 80 if the terminal size cannot be determined.
    """
    try:
        return os.get_terminal_size().columns
    except OSError:
        return int(os.environ.get("COLUMNS", "80"))
