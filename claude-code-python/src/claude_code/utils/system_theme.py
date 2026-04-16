"""System theme detection - Python port of systemTheme.ts.

Detects whether the terminal background is dark or light.
Detection priority:
1. Cached value (set externally via set_cached_system_theme)
2. $COLORFGBG environment variable (synchronous, rxvt-family)
3. Falls back to 'dark'
"""

from __future__ import annotations

import os
import re
from typing import Literal, Optional

SystemTheme = Literal['dark', 'light']

_cached_system_theme: Optional[SystemTheme] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_system_theme_name() -> SystemTheme:
    """Return the current terminal theme, falling back to 'dark'."""
    global _cached_system_theme
    if _cached_system_theme is None:
        _cached_system_theme = _detect_from_colorfgbg() or 'dark'
    return _cached_system_theme


def set_cached_system_theme(theme: SystemTheme) -> None:
    """Update the cached terminal theme (called by async watcher)."""
    global _cached_system_theme
    _cached_system_theme = theme


def detect_system_theme() -> SystemTheme:
    """Alias for get_system_theme_name() — convenience for callers."""
    return get_system_theme_name()


def resolve_theme_setting(setting: str) -> str:
    """Resolve an 'auto' theme setting to a concrete theme name."""
    if setting == 'auto':
        return get_system_theme_name()
    return setting


# ---------------------------------------------------------------------------
# OSC color parsing
# ---------------------------------------------------------------------------

def theme_from_osc_color(data: str) -> Optional[SystemTheme]:
    """Parse an OSC 10/11 color response into a theme.

    Accepts:
    - ``rgb:RRRR/GGGG/BBBB`` (xterm, iTerm2, kitty, …)
    - ``#RRGGBB`` / ``#RRRRGGGGBBBB``

    Returns None for unrecognised formats.
    """
    rgb = _parse_osc_rgb(data)
    if rgb is None:
        return None
    r, g, b = rgb
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return 'light' if luminance > 0.5 else 'dark'


def _hex_component(hex_str: str) -> float:
    """Normalise a 1–4 digit hex component to [0, 1]."""
    max_val = 16 ** len(hex_str) - 1
    return int(hex_str, 16) / max_val


def _parse_osc_rgb(data: str) -> Optional[tuple[float, float, float]]:
    """Parse rgb:/rgba: or #hex colour strings into (r, g, b) ∈ [0,1]³."""
    # rgb:RRRR/GGGG/BBBB (or rgba: with optional alpha)
    m = re.match(r'^rgba?:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})', data)
    if m:
        return (_hex_component(m.group(1)), _hex_component(m.group(2)), _hex_component(m.group(3)))

    # #RRGGBB or #RRRRGGGGBBBB
    m = re.match(r'^#([0-9a-fA-F]+)$', data)
    if m:
        hex_str = m.group(1)
        if len(hex_str) % 3 == 0:
            n = len(hex_str) // 3
            return (
                _hex_component(hex_str[:n]),
                _hex_component(hex_str[n:2*n]),
                _hex_component(hex_str[2*n:]),
            )
    return None


# ---------------------------------------------------------------------------
# COLORFGBG detection
# ---------------------------------------------------------------------------

def _detect_from_colorfgbg() -> Optional[SystemTheme]:
    """Parse $COLORFGBG for a synchronous initial theme guess."""
    colorfgbg = os.environ.get('COLORFGBG')
    if not colorfgbg:
        return None
    parts = colorfgbg.split(';')
    bg = parts[-1] if parts else ''
    if not bg:
        return None
    try:
        bg_num = int(bg)
    except ValueError:
        return None
    if not (0 <= bg_num <= 15):
        return None
    # 0-6 and 8 are dark ANSI colors; 7 and 9-15 are light
    return 'dark' if (bg_num <= 6 or bg_num == 8) else 'light'
