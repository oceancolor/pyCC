# 原始 TS: utils/terminal.ts
"""
Terminal display utilities - text wrapping, truncation, and rendering.
Python equivalent using shutil.get_terminal_size() and ANSI-aware logic.
"""
from __future__ import annotations

import os
import shutil
from typing import Optional


# Max lines to show before truncating
MAX_LINES_TO_SHOW = 3
# Padding to prevent overflow (accounts for message prefix like "  ⎿ ")
PADDING_TO_PREVENT_OVERFLOW = 10


def get_terminal_width() -> int:
    """Get the current terminal width."""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def wrap_text(
    text: str,
    wrap_width: int,
) -> tuple[str, int]:
    """
    Wrap text at the specified width.
    Returns (above_the_fold, remaining_lines).
    原始 TS: wrapText()
    """
    lines = text.split("\n")
    wrapped_lines: list[str] = []

    for line in lines:
        visible_width = len(line)  # simplified: no ANSI-aware width
        if visible_width <= wrap_width:
            wrapped_lines.append(line.rstrip())
        else:
            # Break long lines into chunks
            for i in range(0, visible_width, wrap_width):
                chunk = line[i:i + wrap_width]
                wrapped_lines.append(chunk.rstrip())

    remaining_lines = len(wrapped_lines) - MAX_LINES_TO_SHOW

    # If there's only 1 line after the fold, show it directly
    if remaining_lines == 1:
        above_the_fold = "\n".join(wrapped_lines[:MAX_LINES_TO_SHOW + 1]).rstrip()
        return above_the_fold, 0

    above_the_fold = "\n".join(wrapped_lines[:MAX_LINES_TO_SHOW]).rstrip()
    return above_the_fold, max(0, remaining_lines)


def render_truncated_content(
    content: str,
    terminal_width: Optional[int] = None,
    suppress_expand_hint: bool = False,
) -> str:
    """
    Renders content with line-based truncation for terminal display.
    原始 TS: renderTruncatedContent()
    
    If content exceeds MAX_LINES_TO_SHOW, truncates and adds a hint.
    """
    if terminal_width is None:
        terminal_width = get_terminal_width()

    trimmed = content.rstrip()
    if not trimmed:
        return ""

    wrap_width = max(terminal_width - PADDING_TO_PREVENT_OVERFLOW, 10)

    # Only process enough content for visible lines (performance optimization)
    max_chars = MAX_LINES_TO_SHOW * wrap_width * 4
    pre_truncated = len(trimmed) > max_chars
    content_for_wrapping = trimmed[:max_chars] if pre_truncated else trimmed

    above_the_fold, remaining_lines = wrap_text(content_for_wrapping, wrap_width)

    if pre_truncated:
        estimated_remaining = max(
            remaining_lines,
            (len(trimmed) // wrap_width) - MAX_LINES_TO_SHOW,
        )
    else:
        estimated_remaining = remaining_lines

    if estimated_remaining <= 0:
        return above_the_fold

    if suppress_expand_hint:
        return above_the_fold + f"\n… +{estimated_remaining} line(s)"
    else:
        return above_the_fold + f"\n… +{estimated_remaining} line(s) (ctrl+o to expand)"


def render_tool_use_output(
    content: str,
    terminal_width: Optional[int] = None,
    max_lines: int = MAX_LINES_TO_SHOW,
) -> str:
    """
    Renders tool output for display, with truncation.
    Used for showing tool results in the terminal.
    """
    if terminal_width is None:
        terminal_width = get_terminal_width()

    lines = content.split("\n")
    if len(lines) <= max_lines:
        return content

    above = "\n".join(lines[:max_lines])
    remaining = len(lines) - max_lines
    return f"{above}\n… +{remaining} more line(s)"


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from text."""
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def visible_length(text: str) -> int:
    """Get the visible length of text (ignoring ANSI escape sequences)."""
    return len(strip_ansi(text))


def format_for_terminal(
    text: str,
    indent: str = "",
    max_width: Optional[int] = None,
) -> str:
    """
    Format text for terminal output with optional indentation and wrapping.
    """
    if max_width is None:
        max_width = get_terminal_width()

    if not indent:
        return text

    lines = text.split("\n")
    indented = [indent + line if line.strip() else line for line in lines]
    return "\n".join(indented)


class TerminalRenderer:
    """
    High-level terminal renderer for Claude Code output.
    Manages indentation, color, and truncation.
    """

    def __init__(self, width: Optional[int] = None) -> None:
        self.width = width or get_terminal_width()
        self.use_color = self._detect_color_support()

    def _detect_color_support(self) -> bool:
        """Detect if the terminal supports color."""
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("FORCE_COLOR"):
            return True
        return os.isatty(1)  # stdout

    def render_user_message(self, text: str) -> str:
        """Render a user message."""
        return f"> {text}"

    def render_assistant_message(self, text: str) -> str:
        """Render an assistant message with truncation."""
        return render_truncated_content(text, self.width)

    def render_tool_use(self, tool_name: str, input_summary: str) -> str:
        """Render a tool use indicator."""
        return f"  ⚙ {tool_name}({input_summary})"

    def render_tool_result(self, content: str) -> str:
        """Render a tool result with truncation."""
        truncated = render_truncated_content(content, self.width)
        # Indent with "  ⎿ " prefix
        lines = truncated.split("\n")
        if not lines:
            return ""
        result = "  ⎿ " + lines[0]
        if len(lines) > 1:
            result += "\n" + "\n".join("    " + line for line in lines[1:])
        return result

    def render_error(self, message: str) -> str:
        """Render an error message."""
        if self.use_color:
            try:
                # Try to use colorama if available
                from colorama import Fore, Style
                return f"{Fore.RED}Error: {message}{Style.RESET_ALL}"
            except ImportError:
                pass
        return f"Error: {message}"

    def render_info(self, message: str) -> str:
        """Render an info message."""
        return f"  {message}"
