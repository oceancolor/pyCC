# 原始 TS: utils/truncate.ts
"""Width-aware string / path truncation utilities."""

from __future__ import annotations

import os
import unicodedata
from typing import Optional


# ---------------------------------------------------------------------------
# String-width helpers
# ---------------------------------------------------------------------------

def string_width(s: str) -> int:
    """Return the terminal display width of *s*.

    East-Asian wide characters count as 2; control/zero-width chars as 0;
    everything else as 1.
    """
    width = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ("W", "F"):
            width += 2
        elif eaw in ("Na", "H", "N"):
            width += 1
        # zero-width, combining → 0
    return width


# ---------------------------------------------------------------------------
# Path truncation
# ---------------------------------------------------------------------------

def truncate_path_middle(path: str, max_length: int) -> str:
    """Truncate *path* in the middle, preserving dir context and filename.

    Example: "src/components/deeply/nested/folder/MyComponent.tsx"
    → "src/components/…/MyComponent.tsx" when max_length=30.
    """
    if max_length <= 0:
        return "…"
    if string_width(path) <= max_length:
        return path
    if max_length < 5:
        return truncate_to_width(path, max_length)

    sep = os.sep  # "/" on POSIX, "\\" on Windows
    parts = path.replace("\\", "/").split("/")
    filename = parts[-1] if parts else path

    # If even the filename alone doesn't fit, truncate it from the end
    if string_width(filename) >= max_length:
        return truncate_to_width(filename, max_length)

    # Binary search: keep as many leading path segments as fit
    left: list[str] = []
    right = parts[-1:]
    for part in parts[:-1]:
        candidate = sep.join(left + [part, "…"] + right)
        if string_width(candidate) <= max_length:
            left.append(part)
        else:
            break

    if left:
        return sep.join(left + ["…"] + right)
    return "…" + sep + filename


def truncate_to_width(s: str, max_width: int) -> str:
    """Truncate *s* so its display width ≤ *max_width*, appending "…"."""
    if max_width <= 0:
        return ""
    if string_width(s) <= max_width:
        return s

    result: list[str] = []
    used = 0
    # Reserve 1 column for the ellipsis
    limit = max_width - 1
    for ch in s:
        w = string_width(ch)
        if used + w > limit:
            break
        result.append(ch)
        used += w
    return "".join(result) + "…"


# ---------------------------------------------------------------------------
# Line / output truncation
# ---------------------------------------------------------------------------

def truncate_output(
    text: str,
    max_lines: Optional[int] = None,
    max_chars: Optional[int] = None,
    truncation_notice: str = "\n[Output truncated…]",
) -> str:
    """Truncate *text* to at most *max_lines* lines or *max_chars* characters.

    Returns the (possibly truncated) text with an appended notice when
    truncation occurs.
    """
    truncated = False

    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    if max_lines is not None:
        lines = text.splitlines(keepends=True)
        if len(lines) > max_lines:
            text = "".join(lines[:max_lines])
            truncated = True

    if truncated:
        text += truncation_notice
    return text
