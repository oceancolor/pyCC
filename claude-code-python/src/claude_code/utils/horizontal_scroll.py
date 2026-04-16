"""
Horizontal scroll state management (UI stub).
Ported from horizontalScroll.ts - TUI/React parts stripped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HorizontalScrollState:
    """State for horizontal scroll in terminal output."""
    offset: int = 0
    max_offset: int = 0
    visible_width: int = 80
    content_width: int = 0

    @property
    def can_scroll_left(self) -> bool:
        return self.offset > 0

    @property
    def can_scroll_right(self) -> bool:
        return self.offset < self.max_offset

    def scroll_left(self, amount: int = 1) -> None:
        self.offset = max(0, self.offset - amount)

    def scroll_right(self, amount: int = 1) -> None:
        self.offset = min(self.max_offset, self.offset + amount)

    def reset(self) -> None:
        self.offset = 0

    def update_dimensions(self, visible_width: int, content_width: int) -> None:
        self.visible_width = visible_width
        self.content_width = content_width
        self.max_offset = max(0, content_width - visible_width)
        self.offset = min(self.offset, self.max_offset)


def apply_horizontal_scroll(text: str, offset: int, width: int) -> str:
    """
    Apply horizontal scroll to a single line of text.

    Args:
        text: Input text (may contain ANSI codes - treated as plain here)
        offset: Number of characters to skip from left
        width: Maximum visible width

    Returns:
        Sliced text string
    """
    # Strip ANSI for width calculation (simplified - no ANSI awareness)
    visible = text[offset: offset + width] if offset < len(text) else ""
    return visible


def get_scroll_indicator(state: HorizontalScrollState) -> str:
    """Return a scroll indicator string like '< 40 >'."""
    left = "<" if state.can_scroll_left else " "
    right = ">" if state.can_scroll_right else " "
    return f"{left} {state.offset} {right}"
