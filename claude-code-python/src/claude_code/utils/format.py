"""
Format utilities
原始 TS: src/utils/format.ts
"""
from __future__ import annotations

import math
from typing import Optional


def format_file_size(size_in_bytes: int) -> str:
    """
    Formats a byte count to a human-readable string (KB, MB, GB).
    formatFileSize(1536) → '1.5KB'
    """
    kb = size_in_bytes / 1024
    if kb < 1:
        return f"{size_in_bytes} bytes"
    if kb < 1024:
        s = f"{kb:.1f}"
        if s.endswith(".0"):
            s = s[:-2]
        return f"{s}KB"
    mb = kb / 1024
    if mb < 1024:
        s = f"{mb:.1f}"
        if s.endswith(".0"):
            s = s[:-2]
        return f"{s}MB"
    gb = mb / 1024
    s = f"{gb:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return f"{s}GB"


def format_seconds_short(ms: float) -> str:
    """Format milliseconds as seconds with 1 decimal place. e.g. 1234 → '1.2s'"""
    return f"{ms / 1000:.1f}s"


def format_duration(
    ms: float,
    *,
    hide_trailing_zeros: bool = False,
    most_significant_only: bool = False,
) -> str:
    """Format milliseconds to human-readable duration string."""
    if ms < 60000:
        if ms == 0:
            return "0s"
        if ms < 1:
            return f"{ms / 1000:.1f}s"
        s = int(ms / 1000)
        return f"{s}s"

    days = int(ms // 86400000)
    hours = int((ms % 86400000) // 3600000)
    minutes = int((ms % 3600000) // 60000)
    seconds = round((ms % 60000) / 1000)

    # Handle rounding carry-over
    if seconds == 60:
        seconds = 0
        minutes += 1
    if minutes == 60:
        minutes = 0
        hours += 1
    if hours == 24:
        hours = 0
        days += 1

    if most_significant_only:
        if days > 0:
            return f"{days}d"
        if hours > 0:
            return f"{hours}h"
        if minutes > 0:
            return f"{minutes}m"
        return f"{seconds}s"

    parts: list[str] = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or (not hide_trailing_zeros and days > 0):
        parts.append(f"{hours}h")
    if minutes > 0 or (not hide_trailing_zeros and (days > 0 or hours > 0)):
        parts.append(f"{minutes}m")
    if seconds > 0 or not hide_trailing_zeros:
        parts.append(f"{seconds}s")

    return " ".join(parts) or "0s"


def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to max_length characters."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix
