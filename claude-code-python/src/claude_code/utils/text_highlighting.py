"""
Text highlighting utilities for terminal ANSI output.
Port of textHighlighting.ts — segment text by highlight ranges.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass
class TextHighlight:
    start: int
    end: int
    color: Optional[str] = None          # theme key
    dim_color: bool = False
    inverse: bool = False
    shimmer_color: Optional[str] = None
    priority: int = 0


@dataclass
class TextSegment:
    text: str
    start: int
    highlight: Optional[TextHighlight] = None


# ---------------------------------------------------------------------------
# ANSI helpers (optional pygments fallback)
# ---------------------------------------------------------------------------

try:
    from pygments import highlight as _pygments_highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import TerminalFormatter
    from pygments.util import ClassNotFound
    _PYGMENTS_AVAILABLE = True
except ImportError:
    _PYGMENTS_AVAILABLE = False


def highlight_code(code: str, language: str = "") -> str:
    """Return ANSI-coloured *code* for the given *language*.

    Falls back to returning *code* unchanged when pygments is unavailable
    or the lexer cannot be found.
    """
    if not _PYGMENTS_AVAILABLE:
        return code
    try:
        if language:
            lexer = get_lexer_by_name(language, stripall=False)
        else:
            lexer = guess_lexer(code)
        return _pygments_highlight(code, lexer, TerminalFormatter())
    except Exception:
        return code


# ---------------------------------------------------------------------------
# Core segmentation logic
# ---------------------------------------------------------------------------

def segment_text_by_highlights(
    text: str,
    highlights: list[TextHighlight],
) -> list[TextSegment]:
    """Split *text* into segments according to non-overlapping *highlights*.

    Highlights are resolved in priority order (higher priority wins); any
    overlapping lower-priority highlight is dropped.
    """
    if not highlights:
        return [TextSegment(text=text, start=0)]

    # Sort by start position; break ties by descending priority
    sorted_hl = sorted(highlights, key=lambda h: (h.start, -h.priority))

    resolved: list[TextHighlight] = []
    used: list[tuple[int, int]] = []  # (start, end) of accepted highlights

    for hl in sorted_hl:
        if hl.start == hl.end:
            continue
        overlaps = any(
            not (hl.end <= s or hl.start >= e) for s, e in used
        )
        if not overlaps:
            resolved.append(hl)
            used.append((hl.start, hl.end))

    return _SimpleSegmenter(text).segment(resolved)


class _SimpleSegmenter:
    """Plain-text segmenter (no ANSI token awareness)."""

    def __init__(self, text: str) -> None:
        self._text = text

    def segment(self, highlights: list[TextHighlight]) -> list[TextSegment]:
        segments: list[TextSegment] = []
        pos = 0

        for hl in sorted(highlights, key=lambda h: h.start):
            if pos < hl.start:
                segments.append(TextSegment(
                    text=self._text[pos:hl.start],
                    start=pos,
                ))
            seg = TextSegment(
                text=self._text[hl.start:hl.end],
                start=hl.start,
                highlight=hl,
            )
            segments.append(seg)
            pos = hl.end

        if pos < len(self._text):
            segments.append(TextSegment(text=self._text[pos:], start=pos))

        return segments


# ---------------------------------------------------------------------------
# ANSI colour helpers used by renderers
# ---------------------------------------------------------------------------

ANSI_RESET = "\x1b[0m"


def ansi_color(text: str, color_code: str) -> str:
    """Wrap *text* with a raw ANSI escape *color_code* and reset."""
    return f"\x1b[{color_code}m{text}{ANSI_RESET}"


def dim(text: str) -> str:
    return ansi_color(text, "2")


def inverse(text: str) -> str:
    return ansi_color(text, "7")
