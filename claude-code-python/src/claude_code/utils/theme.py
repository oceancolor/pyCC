"""
Theme system — Python equivalent of theme.ts.

Provides three built-in color themes (dark, light, claude) as data-only
dictionaries.  All ink/React/chalk rendering is intentionally excluded.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class ColorTheme:
    """
    A named color palette.

    ``colors`` maps semantic color keys to CSS-style ``rgb(r,g,b)`` strings
    (or ANSI color names for ANSI-only themes).
    """

    name: str
    colors: Dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = "") -> str:
        """Return the color for *key*, falling back to *default*."""
        return self.colors.get(key, default)


# ---------------------------------------------------------------------------
# Built-in theme definitions
# Values are taken directly from theme.ts (light / dark themes).
# Only the three canonical themes (dark, light, claude) are included;
# ANSI / daltonized variants are intentionally omitted to stay under 200 lines.
# ---------------------------------------------------------------------------

_DARK_COLORS: Dict[str, str] = {
    "autoAccept": "rgb(175,135,255)",
    "bashBorder": "rgb(253,93,177)",
    "claude": "rgb(215,119,87)",
    "claudeShimmer": "rgb(235,159,127)",
    "permission": "rgb(177,185,249)",
    "planMode": "rgb(72,150,140)",
    "ide": "rgb(71,130,200)",
    "promptBorder": "rgb(136,136,136)",
    "text": "rgb(255,255,255)",
    "inverseText": "rgb(0,0,0)",
    "inactive": "rgb(153,153,153)",
    "subtle": "rgb(80,80,80)",
    "suggestion": "rgb(177,185,249)",
    "remember": "rgb(177,185,249)",
    "background": "rgb(0,204,204)",
    "success": "rgb(78,186,101)",
    "error": "rgb(255,107,128)",
    "warning": "rgb(255,193,7)",
    "merged": "rgb(175,135,255)",
    "diffAdded": "rgb(34,92,43)",
    "diffRemoved": "rgb(122,41,54)",
    "diffAddedWord": "rgb(56,166,96)",
    "diffRemovedWord": "rgb(179,89,107)",
    "red_FOR_SUBAGENTS_ONLY": "rgb(220,38,38)",
    "blue_FOR_SUBAGENTS_ONLY": "rgb(37,99,235)",
    "green_FOR_SUBAGENTS_ONLY": "rgb(22,163,74)",
    "yellow_FOR_SUBAGENTS_ONLY": "rgb(202,138,4)",
    "purple_FOR_SUBAGENTS_ONLY": "rgb(147,51,234)",
    "orange_FOR_SUBAGENTS_ONLY": "rgb(234,88,12)",
    "pink_FOR_SUBAGENTS_ONLY": "rgb(219,39,119)",
    "cyan_FOR_SUBAGENTS_ONLY": "rgb(8,145,178)",
    "userMessageBackground": "rgb(55,55,55)",
    "selectionBg": "rgb(38,79,120)",
    "fastMode": "rgb(255,120,20)",
    "briefLabelYou": "rgb(122,180,232)",
    "briefLabelClaude": "rgb(215,119,87)",
    "rainbow_red": "rgb(235,95,87)",
    "rainbow_orange": "rgb(245,139,87)",
    "rainbow_yellow": "rgb(250,195,95)",
    "rainbow_green": "rgb(145,200,130)",
    "rainbow_blue": "rgb(130,170,220)",
    "rainbow_indigo": "rgb(155,130,200)",
    "rainbow_violet": "rgb(200,130,180)",
}

_LIGHT_COLORS: Dict[str, str] = {
    "autoAccept": "rgb(135,0,255)",
    "bashBorder": "rgb(255,0,135)",
    "claude": "rgb(215,119,87)",
    "claudeShimmer": "rgb(245,149,117)",
    "permission": "rgb(87,105,247)",
    "planMode": "rgb(0,102,102)",
    "ide": "rgb(71,130,200)",
    "promptBorder": "rgb(153,153,153)",
    "text": "rgb(0,0,0)",
    "inverseText": "rgb(255,255,255)",
    "inactive": "rgb(102,102,102)",
    "subtle": "rgb(175,175,175)",
    "suggestion": "rgb(87,105,247)",
    "remember": "rgb(0,0,255)",
    "background": "rgb(0,153,153)",
    "success": "rgb(44,122,57)",
    "error": "rgb(171,43,63)",
    "warning": "rgb(150,108,30)",
    "merged": "rgb(135,0,255)",
    "diffAdded": "rgb(105,219,124)",
    "diffRemoved": "rgb(255,168,180)",
    "diffAddedWord": "rgb(47,157,68)",
    "diffRemovedWord": "rgb(209,69,75)",
    "red_FOR_SUBAGENTS_ONLY": "rgb(220,38,38)",
    "blue_FOR_SUBAGENTS_ONLY": "rgb(37,99,235)",
    "green_FOR_SUBAGENTS_ONLY": "rgb(22,163,74)",
    "yellow_FOR_SUBAGENTS_ONLY": "rgb(202,138,4)",
    "purple_FOR_SUBAGENTS_ONLY": "rgb(147,51,234)",
    "orange_FOR_SUBAGENTS_ONLY": "rgb(234,88,12)",
    "pink_FOR_SUBAGENTS_ONLY": "rgb(219,39,119)",
    "cyan_FOR_SUBAGENTS_ONLY": "rgb(8,145,178)",
    "userMessageBackground": "rgb(240,240,240)",
    "selectionBg": "rgb(180,213,255)",
    "fastMode": "rgb(255,106,0)",
    "briefLabelYou": "rgb(37,99,235)",
    "briefLabelClaude": "rgb(215,119,87)",
    "rainbow_red": "rgb(235,95,87)",
    "rainbow_orange": "rgb(245,139,87)",
    "rainbow_yellow": "rgb(250,195,95)",
    "rainbow_green": "rgb(145,200,130)",
    "rainbow_blue": "rgb(130,170,220)",
    "rainbow_indigo": "rgb(155,130,200)",
    "rainbow_violet": "rgb(200,130,180)",
}

# "claude" theme: same palette as dark but with the brand orange as the
# primary accent (consistent with the claude.ai web app aesthetic).
_CLAUDE_COLORS: Dict[str, str] = {
    **_DARK_COLORS,
    "claude": "rgb(215,119,87)",          # prominent brand orange
    "suggestion": "rgb(215,119,87)",
    "remember": "rgb(215,119,87)",
    "briefLabelClaude": "rgb(215,119,87)",
}

BUILT_IN_THEMES: Dict[str, ColorTheme] = {
    "dark": ColorTheme(name="dark", colors=deepcopy(_DARK_COLORS)),
    "light": ColorTheme(name="light", colors=deepcopy(_LIGHT_COLORS)),
    "claude": ColorTheme(name="claude", colors=deepcopy(_CLAUDE_COLORS)),
}

# ---------------------------------------------------------------------------
# Global theme state
# ---------------------------------------------------------------------------

_current_theme_name: str = "dark"


def get_theme(name: str) -> ColorTheme:
    """
    Return the :class:`ColorTheme` for *name*.

    Falls back to the ``"dark"`` theme if *name* is not recognised.
    """
    return BUILT_IN_THEMES.get(name, BUILT_IN_THEMES["dark"])


def get_current_theme() -> ColorTheme:
    """Return the currently active global theme."""
    return get_theme(_current_theme_name)


def set_theme(name: str) -> None:
    """
    Set the global active theme.

    Parameters
    ----------
    name:
        Theme name.  Must be one of ``"dark"``, ``"light"``, ``"claude"``
        (or any key in :data:`BUILT_IN_THEMES`).

    Raises
    ------
    ValueError
        If *name* is not a recognised built-in theme.
    """
    if name not in BUILT_IN_THEMES:
        raise ValueError(
            f"Unknown theme {name!r}. Available: {list(BUILT_IN_THEMES)}"
        )
    global _current_theme_name
    _current_theme_name = name
