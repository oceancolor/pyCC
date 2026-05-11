"""Ink/terminal color utilities. Ported from utils/ink.ts"""
from __future__ import annotations
from typing import Optional

DEFAULT_AGENT_THEME_COLOR = "cyan_FOR_SUBAGENTS_ONLY"

# Mapping from AgentColorName → theme color key, mirrors agentColorManager.ts
AGENT_COLOR_TO_THEME_COLOR: dict = {
    "blue": "blue",
    "green": "green",
    "yellow": "yellow",
    "magenta": "magenta",
    "cyan": "cyan",
    "red": "red",
    "white": "white",
    "gray": "gray",
    "orange": "orange",
    "pink": "pink",
}


def to_ink_color(color: Optional[str]) -> str:
    """Convert a color string to an Ink-compatible TextProps color value.

    Colors are typically AgentColorName values like ``'blue'``, ``'green'``,
    etc. Known agent colors are mapped to their theme key; unknown colors fall
    back to a raw ``ansi:<color>`` string.

    Args:
        color: A color name string, or ``None`` to get the default subagent color.

    Returns:
        A color string suitable for use as an Ink ``TextProps['color']`` value.
    """
    if not color:
        return DEFAULT_AGENT_THEME_COLOR
    theme_color = AGENT_COLOR_TO_THEME_COLOR.get(color)
    if theme_color:
        return theme_color
    return f"ansi:{color}"
