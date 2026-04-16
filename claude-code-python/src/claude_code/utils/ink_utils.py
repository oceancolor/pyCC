"""Ink color utilities stub. Ported from ink.ts"""
from __future__ import annotations
from typing import Optional

DEFAULT_AGENT_THEME_COLOR = 'cyan_FOR_SUBAGENTS_ONLY'

def to_ink_color(color: Optional[str]) -> str:
    if not color:
        return DEFAULT_AGENT_THEME_COLOR
    AGENT_COLOR_MAP = {'blue':'blue','green':'green','red':'red','yellow':'yellow',
                       'cyan':'cyan','magenta':'magenta','white':'white'}
    return AGENT_COLOR_MAP.get(color, f'ansi:{color}')
