"""Task output formatting utilities. Ported from utils/task/outputFormatting.ts"""

from __future__ import annotations

import re
from typing import Optional

# Maximum number of lines to display in a task status notification
MAX_DISPLAY_LINES = 10

# Maximum number of characters per line before truncation
MAX_LINE_CHARS = 200


def format_task_output_for_display(
    output: str,
    max_lines: int = MAX_DISPLAY_LINES,
    max_line_chars: int = MAX_LINE_CHARS,
) -> str:
    """Format raw task output for display in a notification or status panel.

    - Strips trailing whitespace from each line.
    - Truncates very long lines with an ellipsis.
    - Returns at most ``max_lines`` of the most-recent output.
    - Prefixes with ``"…"`` when lines are omitted from the beginning.

    Args:
        output: Raw stdout/stderr text.
        max_lines: Maximum number of lines to include in the result.
        max_line_chars: Maximum characters per line.

    Returns:
        A concise, human-readable summary of the output.
    """
    if not output:
        return ""

    lines = output.splitlines()
    # Strip trailing blank lines
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        return ""

    # Truncate individual lines
    truncated = []
    for line in lines:
        stripped = line.rstrip()
        if len(stripped) > max_line_chars:
            stripped = stripped[:max_line_chars] + "…"
        truncated.append(stripped)

    if len(truncated) <= max_lines:
        return "\n".join(truncated)

    # Take the last max_lines lines
    prefix = "…"
    tail = truncated[-max_lines:]
    return prefix + "\n" + "\n".join(tail)


def format_delta_summary(
    new_output: str,
    max_lines: int = 5,
    max_line_chars: int = MAX_LINE_CHARS,
) -> Optional[str]:
    """Format a delta (incremental) output chunk for display.

    Args:
        new_output: The new output since the last notification.
        max_lines: Maximum lines to include.
        max_line_chars: Maximum characters per line.

    Returns:
        A formatted string, or None if there is nothing to show.
    """
    if not new_output or not new_output.strip():
        return None

    return format_task_output_for_display(new_output, max_lines, max_line_chars)


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*[mGKHFJABCDST]|\x1b[()][AB012]')
    return ansi_escape.sub("", text)


def estimate_line_count(text: str) -> int:
    """Return the number of non-empty lines in ``text``."""
    return sum(1 for line in text.splitlines() if line.strip())
