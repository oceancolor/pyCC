"""Ultraplan/ultrareview keyword detection. Ported from utils/ultraplan/keyword.ts"""

from __future__ import annotations

import re
from typing import List, Optional

# Paired-delimiter open→close map
_OPEN_TO_CLOSE: dict = {
    "`": "`",
    '"': '"',
    "<": ">",
    "{": "}",
    "[": "]",
    "(": ")",
    "'": "'",
}

_WORD_RE = re.compile(r'[\w]', re.UNICODE)


def _is_word_char(ch: Optional[str]) -> bool:
    return bool(ch and _WORD_RE.match(ch))


def _find_quoted_ranges(text: str) -> List[tuple]:
    """Find ranges covered by paired delimiters (quotes, brackets, etc.)."""
    ranges: List[tuple] = []
    open_quote: Optional[str] = None
    open_at = 0

    for i, ch in enumerate(text):
        if open_quote is None:
            # Check for valid opening delimiters
            if ch == "<" and i + 1 < len(text) and re.match(r'[a-zA-Z/]', text[i + 1]):
                open_quote = ch
                open_at = i
            elif ch == "'" and not _is_word_char(text[i - 1] if i > 0 else None):
                open_quote = ch
                open_at = i
            elif ch not in ("<", "'") and ch in _OPEN_TO_CLOSE:
                open_quote = ch
                open_at = i
        else:
            # Handle nested [[ inside [ (for [Pasted text #N] placeholders)
            if open_quote == "[" and ch == "[":
                open_at = i
                continue
            if ch != _OPEN_TO_CLOSE[open_quote]:
                continue
            if open_quote == "'" and _is_word_char(text[i + 1] if i + 1 < len(text) else None):
                continue
            ranges.append((open_at, i + 1))
            open_quote = None

    return ranges


def _find_keyword_positions(text: str, keyword: str) -> List[dict]:
    """Find all triggerable occurrences of ``keyword`` in ``text``.

    Skips occurrences inside paired delimiters, path/identifier contexts,
    or when followed by ``?``. Slash-command input (starts with ``/``) is skipped entirely.
    """
    if not re.search(keyword, text, re.IGNORECASE):
        return []
    if text.startswith("/"):
        return []

    quoted_ranges = _find_quoted_ranges(text)

    positions: List[dict] = []
    word_re = re.compile(rf'\b{keyword}\b', re.IGNORECASE)

    for match in word_re.finditer(text):
        start = match.start()
        end = match.end()

        # Skip if inside a quoted/bracketed range
        if any(r[0] <= start < r[1] for r in quoted_ranges):
            continue

        before = text[start - 1] if start > 0 else None
        after = text[end] if end < len(text) else None

        # Skip path/identifier context
        if before in ("/", "\\", "-"):
            continue
        if after in ("/", "\\", "-", "?"):
            continue
        if after == "." and _is_word_char(text[end + 1] if end + 1 < len(text) else None):
            continue

        positions.append({"word": match.group(), "start": start, "end": end})

    return positions


def find_ultraplan_trigger_positions(text: str) -> List[dict]:
    """Return trigger positions of 'ultraplan' in text."""
    return _find_keyword_positions(text, "ultraplan")


def find_ultrareview_trigger_positions(text: str) -> List[dict]:
    """Return trigger positions of 'ultrareview' in text."""
    return _find_keyword_positions(text, "ultrareview")


def has_ultraplan_keyword(text: str) -> bool:
    """Return True if text contains a triggerable 'ultraplan' keyword."""
    return len(find_ultraplan_trigger_positions(text)) > 0


def has_ultrareview_keyword(text: str) -> bool:
    """Return True if text contains a triggerable 'ultrareview' keyword."""
    return len(find_ultrareview_trigger_positions(text)) > 0


def replace_ultraplan_keyword(text: str) -> str:
    """Replace the first triggerable 'ultraplan' with 'plan'.

    Preserves the user's casing of the 'plan' suffix.
    Returns the text unchanged if there is no triggerable occurrence,
    or empty string if the only content was the keyword itself.
    """
    positions = find_ultraplan_trigger_positions(text)
    if not positions:
        return text
    trigger = positions[0]
    before = text[: trigger["start"]]
    after = text[trigger["end"]:]
    if not (before + after).strip():
        return ""
    # Preserve casing of the 'plan' suffix from the original keyword
    suffix = trigger["word"][len("ultra"):]  # 'plan' in original case
    return before + suffix + after
