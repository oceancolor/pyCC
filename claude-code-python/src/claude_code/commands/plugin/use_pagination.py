"""
Ported from: commands/plugin/usePagination.ts

Pagination helper for CLI-rendered lists (replaces the React usePagination hook).

The original is a React hook; this Python version exposes the same logic as a
plain dataclass / callable, suitable for use inside a terminal UI loop.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Generic, List, Optional, TypeVar

T = TypeVar("T")

DEFAULT_MAX_VISIBLE = 5


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScrollPosition:
    """Mirror of the ``scrollPosition`` field in UsePaginationResult."""
    current: int
    total: int
    can_scroll_up: bool
    can_scroll_down: bool


@dataclass
class Pagination(Generic[T]):
    """
    Stateful pagination object for a list of items.

    This is the Python equivalent of the ``UsePaginationResult<T>`` interface
    returned by the ``usePagination`` React hook.
    """
    total_items: int
    max_visible: int = DEFAULT_MAX_VISIBLE
    selected_index: int = 0

    # Computed fields (set in __post_init__)
    _scroll_offset: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._scroll_offset = 0
        self._update_scroll()

    # ------------------------------------------------------------------
    # Public API (mirrors UsePaginationResult)
    # ------------------------------------------------------------------

    @property
    def needs_pagination(self) -> bool:
        return self.total_items > self.max_visible

    @property
    def start_index(self) -> int:
        return self._scroll_offset

    @property
    def end_index(self) -> int:
        return min(self._scroll_offset + self.max_visible, self.total_items)

    @property
    def page_size(self) -> int:
        return self.max_visible

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total_items / self.max_visible))

    @property
    def current_page(self) -> int:
        return self._scroll_offset // self.max_visible

    @property
    def scroll_position(self) -> ScrollPosition:
        return ScrollPosition(
            current=self.selected_index + 1,
            total=self.total_items,
            can_scroll_up=self._scroll_offset > 0,
            can_scroll_down=self._scroll_offset + self.max_visible < self.total_items,
        )

    def get_visible_items(self, items: List[T]) -> List[T]:
        """Return the slice of *items* that is currently visible."""
        if not self.needs_pagination:
            return items
        return items[self.start_index:self.end_index]

    def to_actual_index(self, visible_index: int) -> int:
        """Convert a visible-list index to the actual (full-list) index."""
        return self.start_index + visible_index

    def is_on_current_page(self, actual_index: int) -> bool:
        """Return True if *actual_index* is within the current visible window."""
        return self.start_index <= actual_index < self.end_index

    def go_to_page(self, page: int) -> None:  # noqa: ARG002
        """No-op — scrolling is driven by ``selected_index``."""

    def next_page(self) -> None:
        """No-op — scrolling is driven by ``selected_index``."""

    def prev_page(self) -> None:
        """No-op — scrolling is driven by ``selected_index``."""

    def handle_selection_change(
        self,
        new_index: int,
        set_selected_index: Callable[[int], None],
    ) -> None:
        """
        Clamp *new_index* to valid range, update selected index, and scroll.

        Parameters
        ----------
        new_index:
            The newly requested selection index.
        set_selected_index:
            Callback that persists the updated index in the caller's state.
        """
        clamped = max(0, min(new_index, self.total_items - 1))
        set_selected_index(clamped)
        self.selected_index = clamped
        self._update_scroll()

    def handle_page_navigation(
        self,
        direction: str,
        set_selected_index: Callable[[int], None],  # noqa: ARG002
    ) -> bool:
        """
        Page-level navigation (left/right).  Returns False for continuous
        scrolling (no page jumps needed).
        """
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_scroll(self) -> None:
        """Recompute ``_scroll_offset`` so the selected item stays visible."""
        if not self.needs_pagination:
            self._scroll_offset = 0
            return

        offset = self._scroll_offset

        if self.selected_index < offset:
            self._scroll_offset = self.selected_index
        elif self.selected_index >= offset + self.max_visible:
            self._scroll_offset = self.selected_index - self.max_visible + 1
        else:
            max_offset = max(0, self.total_items - self.max_visible)
            self._scroll_offset = min(offset, max_offset)


# ---------------------------------------------------------------------------
# Factory function (mirrors the usePagination() hook call signature)
# ---------------------------------------------------------------------------

def use_pagination(
    total_items: int,
    max_visible: int = DEFAULT_MAX_VISIBLE,
    selected_index: int = 0,
) -> Pagination:
    """
    Create a :class:`Pagination` instance with the given parameters.

    This is the Python equivalent of calling ``usePagination({...})`` in React.
    """
    p = Pagination(
        total_items=total_items,
        max_visible=max_visible,
        selected_index=selected_index,
    )
    return p
