"""
slice_ansi.py - ANSI string slicing while preserving escape codes.

Ported from sliceAnsi.ts. Uses the `wcwidth` library for display-width
calculation, and `re` for tokenizing ANSI escape sequences.

Display-width semantics: start/end are in "display cells" (same as
stringWidth / wcwidth), not byte/code-unit indices.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Matches a single ANSI escape sequence (CSI, OSC, or other ESC sequences)
_ANSI_RE = re.compile(
    r"""
    (\x1b       # ESC
      (?:
        \[[0-9;?]*[A-Za-z]          # CSI sequences  e.g. \x1b[1;32m
        | \]8;;[^\x07\x1b]*(?:\x07|\x1b\\)  # OSC 8 hyperlink open
        | \]8;[^\x07\x1b]*(?:\x07|\x1b\\)   # OSC 8 (params variant)
        | \][^\x07\x1b]*(?:\x07|\x1b\\)     # generic OSC
        | [^[\]]                             # two-char ESC sequences
      )
    )
""",
    re.VERBOSE,
)


def _char_width(ch: str) -> int:
    """Return display width of a single character (0, 1, or 2)."""
    try:
        from wcwidth import wcwidth  # type: ignore

        w = wcwidth(ch)
        return max(0, w)
    except ImportError:
        # Fallback: use unicodedata east_asian_width
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ("W", "F"):
            return 2
        cat = unicodedata.category(ch)
        if cat in ("Mn", "Me", "Cf"):
            return 0
        return 1


def _str_display_width(s: str) -> int:
    return sum(_char_width(c) for c in s)


def slice_ansi(text: str, start: int, end: Optional[int] = None) -> str:
    """
    Slice *text* (which may contain ANSI escape codes) by display-cell
    positions [start, end).  Escape codes are preserved / restored so the
    returned string is self-contained.
    """
    tokens: list[tuple[str, str]] = []  # (kind, value) where kind='ansi'|'text'
    pos = 0
    for m in _ANSI_RE.finditer(text):
        if m.start() > pos:
            tokens.append(("text", text[pos : m.start()]))
        tokens.append(("ansi", m.group(0)))
        pos = m.end()
    if pos < len(text):
        tokens.append(("text", text[pos:]))

    active_codes: list[str] = []
    position = 0
    result = ""
    include = False

    for kind, value in tokens:
        if kind == "ansi":
            active_codes.append(value)
            if include:
                result += value
        else:
            # Iterate character by character within the text token
            for ch in value:
                width = _char_width(ch)

                if end is not None and position >= end:
                    if width > 0 or not include:
                        break
                    # zero-width combining mark after end — keep if already including
                    # (mirrors TS: keep combining marks that attach to last base char)
                    if include:
                        result += ch
                    continue

                if not include and position >= start:
                    if start > 0 and width == 0:
                        position += width
                        continue
                    include = True
                    result = "".join(active_codes)  # emit active codes at boundary

                if include:
                    result += ch

                position += width

    # Close any still-active style codes (simplified: emit resets)
    if active_codes and include:
        # Emit a reset if any code looks like a style opener
        style_codes = [c for c in active_codes if not c.endswith("m\x1b[0m") and "m" in c]
        if style_codes:
            result += "\x1b[0m"

    return result
