"""LogoV2 layout and display utilities. Ported from utils/logoV2Utils.ts"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Optional, Tuple

# Layout constants
MAX_LEFT_WIDTH = 50
MAX_USERNAME_LENGTH = 20
BORDER_PADDING = 4
DIVIDER_WIDTH = 1
CONTENT_PADDING = 2

LayoutMode = Literal["horizontal", "compact"]


@dataclass
class LayoutDimensions:
    """Column widths for the LogoV2 component."""

    left_width: int
    right_width: int
    total_width: int


def get_layout_mode(columns: int) -> LayoutMode:
    """Determine the layout mode based on terminal width.

    Args:
        columns: Terminal width in columns.

    Returns:
        ``'horizontal'`` for wide terminals (≥ 70 cols), else ``'compact'``.
    """
    return "horizontal" if columns >= 70 else "compact"


def calculate_layout_dimensions(
    columns: int,
    layout_mode: LayoutMode,
    optimal_left_width: int,
) -> LayoutDimensions:
    """Calculate layout dimensions for the LogoV2 component.

    Args:
        columns: Terminal width in columns.
        layout_mode: ``'horizontal'`` or ``'compact'``.
        optimal_left_width: Desired width for the left panel.

    Returns:
        A :class:`LayoutDimensions` instance.
    """
    if layout_mode == "horizontal":
        left_width = optimal_left_width
        used_space = BORDER_PADDING + CONTENT_PADDING + DIVIDER_WIDTH + left_width
        available_for_right = columns - used_space

        right_width = max(30, available_for_right)
        total_width = min(
            left_width + right_width + DIVIDER_WIDTH + CONTENT_PADDING,
            columns - BORDER_PADDING,
        )
        # Recalculate right width if we had to cap total
        right_width = total_width - left_width - DIVIDER_WIDTH - CONTENT_PADDING
        return LayoutDimensions(
            left_width=left_width,
            right_width=max(20, right_width),
            total_width=total_width,
        )
    else:
        # Compact: use full available width
        total_width = max(30, columns - BORDER_PADDING)
        return LayoutDimensions(
            left_width=total_width,
            right_width=total_width,
            total_width=total_width,
        )


def get_terminal_columns() -> int:
    """Return the current terminal width, defaulting to 80."""
    try:
        return os.get_terminal_size().columns
    except OSError:
        return int(os.environ.get("COLUMNS", "80"))


def truncate_to_width(text: str, max_width: int, ellipsis: str = "…") -> str:
    """Truncate ``text`` to at most ``max_width`` characters, appending an ellipsis."""
    if len(text) <= max_width:
        return text
    return text[: max(0, max_width - len(ellipsis))] + ellipsis


def format_subscription_badge(subscription_name: Optional[str]) -> str:
    """Format the subscription tier name for display in the logo banner."""
    if not subscription_name:
        return ""
    name = subscription_name.strip()
    if len(name) > 15:
        name = truncate_to_width(name, 15)
    return f"[{name}]"


def calculate_optimal_left_width(
    username: str,
    cwd_display: str,
    subscription_badge: str = "",
) -> int:
    """Calculate the optimal width for the left panel.

    Takes the maximum of the username length and cwd_display length, capped
    at ``MAX_LEFT_WIDTH``.

    Args:
        username: The display username string.
        cwd_display: The displayed working directory path string.
        subscription_badge: Optional subscription badge string.

    Returns:
        The optimal left panel width in columns.
    """
    username_display = username[:MAX_USERNAME_LENGTH]
    left_items = [username_display, cwd_display, subscription_badge]
    max_item_width = max(len(item) for item in left_items if item)
    return min(max_item_width, MAX_LEFT_WIDTH)
