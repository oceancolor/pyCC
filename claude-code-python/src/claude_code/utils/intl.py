"""
Intl - Internationalisation / localisation utilities.

Python port of intl.ts.

All instances are lazily initialised and cached for the process lifetime
(mirrors the TS approach of caching Intl constructors to avoid repeated
construction overhead).

Public API
----------
get_grapheme_segmenter()     → regex-based grapheme helper (stub)
first_grapheme(text)         → str
last_grapheme(text)          → str
get_word_segmenter()         → simple whitespace-based helper (stub)
get_relative_time_format()   → cached RelativeTimeFormatter
get_time_zone()              → str (e.g. "Asia/Shanghai")
get_system_locale_language() → str | None (e.g. "en", "ja")
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Grapheme segmentation
# ---------------------------------------------------------------------------
# Python's `unicodedata` + regex library provides grapheme cluster support.
# We use a lightweight regex-based approach; callers that need full Unicode
# cluster support should install the `regex` package and replace this.


def _split_graphemes(text: str) -> list[str]:
    """Split *text* into a list of grapheme clusters (best-effort)."""
    # regex package provides \X for grapheme clusters; fall back to list(text)
    try:
        import regex  # type: ignore[import]

        return regex.findall(r"\X", text)
    except ImportError:
        # Naive fallback: treat each code-point as a grapheme
        return list(text)


class _GraphemeSegmenter:
    """Thin wrapper that mimics a segmenter interface."""

    def segment(self, text: str) -> list[str]:  # noqa: D401
        return _split_graphemes(text)


_grapheme_segmenter: Optional[_GraphemeSegmenter] = None


def get_grapheme_segmenter() -> _GraphemeSegmenter:
    """Return the cached grapheme segmenter instance."""
    global _grapheme_segmenter
    if _grapheme_segmenter is None:
        _grapheme_segmenter = _GraphemeSegmenter()
    return _grapheme_segmenter


def first_grapheme(text: str) -> str:
    """Return the first grapheme cluster of *text*, or '' if empty."""
    if not text:
        return ""
    clusters = get_grapheme_segmenter().segment(text)
    return clusters[0] if clusters else ""


def last_grapheme(text: str) -> str:
    """Return the last grapheme cluster of *text*, or '' if empty."""
    if not text:
        return ""
    clusters = get_grapheme_segmenter().segment(text)
    return clusters[-1] if clusters else ""


# ---------------------------------------------------------------------------
# Word segmentation (stub)
# ---------------------------------------------------------------------------


class _WordSegmenter:
    """Simple whitespace-based word segmenter."""

    def segment(self, text: str) -> list[str]:  # noqa: D401
        return re.findall(r"\S+", text)


_word_segmenter: Optional[_WordSegmenter] = None


def get_word_segmenter() -> _WordSegmenter:
    """Return the cached word segmenter instance."""
    global _word_segmenter
    if _word_segmenter is None:
        _word_segmenter = _WordSegmenter()
    return _word_segmenter


# ---------------------------------------------------------------------------
# RelativeTimeFormat (simple Python implementation)
# ---------------------------------------------------------------------------

_rtf_cache: dict[str, "_RelativeTimeFormat"] = {}


class _RelativeTimeFormat:
    """Lightweight relative-time formatter (en locale)."""

    def __init__(
        self,
        style: Literal["long", "short", "narrow"],
        numeric: Literal["always", "auto"],
    ) -> None:
        self.style = style
        self.numeric = numeric

    def format(self, value: float, unit: str) -> str:  # noqa: D401
        past = value < 0
        abs_val = abs(int(value))
        label = f"{abs_val} {unit}{'s' if abs_val != 1 else ''}"
        if self.numeric == "auto" and abs_val == 1:
            if unit == "day":
                return "yesterday" if past else "tomorrow"
            if unit == "hour" and not past:
                return "next hour"
        direction = "ago" if past else "from now"
        return f"{label} {direction}"


def get_relative_time_format(
    style: Literal["long", "short", "narrow"],
    numeric: Literal["always", "auto"],
) -> _RelativeTimeFormat:
    """Return a cached RelativeTimeFormat for the given style/numeric combo."""
    key = f"{style}:{numeric}"
    if key not in _rtf_cache:
        _rtf_cache[key] = _RelativeTimeFormat(style, numeric)
    return _rtf_cache[key]


# ---------------------------------------------------------------------------
# Timezone & locale language (process-lifetime caches)
# ---------------------------------------------------------------------------

_cached_time_zone: Optional[str] = None


def get_time_zone() -> str:
    """Return the local timezone name (e.g. 'Asia/Shanghai')."""
    global _cached_time_zone
    if _cached_time_zone is None:
        try:
            # Python 3.9+ datetime.now().astimezone().tzname() may return offset
            # strings.  Use zoneinfo/dateutil for a proper IANA name when available.
            import zoneinfo  # Python 3.9+

            _cached_time_zone = str(datetime.now(zoneinfo.ZoneInfo("localtime")).tzinfo)  # type: ignore[arg-type]
        except Exception:
            _cached_time_zone = (
                datetime.now(timezone.utc).astimezone().tzname() or "UTC"
            )
    return _cached_time_zone


_cached_locale_language: Optional[str] = None
_locale_computed: bool = False


def get_system_locale_language() -> Optional[str]:
    """Return the system locale language subtag (e.g. 'en', 'ja'), or None."""
    global _cached_locale_language, _locale_computed
    if not _locale_computed:
        _locale_computed = True
        try:
            import locale

            lang, _ = locale.getlocale()
            if lang:
                _cached_locale_language = lang.split("_")[0].split("-")[0]
        except Exception:
            _cached_locale_language = None
    return _cached_locale_language
