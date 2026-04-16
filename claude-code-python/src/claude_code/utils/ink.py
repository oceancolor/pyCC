"""Ink color helpers. Ported from utils/ink.ts"""
from __future__ import annotations
from typing import Optional

DEFAULT_AGENT_THEME_COLOR = "cyan_FOR_SUBAGENTS_ONLY"


def to_ink_color(color: Optional[str]) -> str:
    """Convert an agent color name to a theme color key."""
    if not color:
        return DEFAULT_AGENT_THEME_COLOR
    try:
        from claude_code.tools.agent_tool.agent_color_manager import AGENT_COLOR_TO_THEME_COLOR
        theme = AGENT_COLOR_TO_THEME_COLOR.get(color)
        if theme:
            return theme
    except ImportError:
        pass
    return f"ansi:{color}"
