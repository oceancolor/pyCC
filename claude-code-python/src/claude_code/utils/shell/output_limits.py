"""
output_limits.py - Output size limiting for shell commands.

Port of TypeScript outputLimits.ts.
"""

import os
from typing import Optional, Tuple

# Default limits
HEAD_LINES = 100
TAIL_LINES = 100
MAX_LINES = HEAD_LINES + TAIL_LINES
MAX_CHARS = 5 * 1024 * 1024  # 5MB
MAX_OUTPUT_CHARS = 500_000  # 500KB


def get_head_lines() -> int:
    """Get configured head lines."""
    try:
        return int(os.environ.get('CLAUDE_CODE_OUTPUT_HEAD_LINES', str(HEAD_LINES)))
    except (ValueError, TypeError):
        return HEAD_LINES


def get_tail_lines() -> int:
    """Get configured tail lines."""
    try:
        return int(os.environ.get('CLAUDE_CODE_OUTPUT_TAIL_LINES', str(TAIL_LINES)))
    except (ValueError, TypeError):
        return TAIL_LINES


def truncate_output(
    output: str,
    max_lines: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> Tuple[str, bool]:
    """
    Truncate shell output if it exceeds limits.

    Args:
        output: The output to truncate
        max_lines: Max number of lines (default: HEAD + TAIL lines)
        max_chars: Max number of characters

    Returns:
        Tuple of (truncated_output, was_truncated)
    """
    if not output:
        return output, False

    actual_max_chars = max_chars or MAX_OUTPUT_CHARS
    actual_head = get_head_lines()
    actual_tail = get_tail_lines()
    actual_max_lines = max_lines or (actual_head + actual_tail)

    # Check character limit first
    if len(output) > actual_max_chars:
        head_chars = actual_max_chars // 2
        tail_chars = actual_max_chars - head_chars

        head_part = output[:head_chars]
        tail_part = output[-tail_chars:]
        omitted = len(output) - head_chars - tail_chars

        result = (
            head_part
            + f"\n\n... [{omitted} characters omitted] ...\n\n"
            + tail_part
        )
        return result, True

    # Check line limit
    lines = output.split('\n')
    if len(lines) <= actual_max_lines:
        return output, False

    head = lines[:actual_head]
    tail = lines[-actual_tail:]
    omitted = len(lines) - actual_head - actual_tail

    result = '\n'.join(head) + f"\n\n... [{omitted} lines omitted] ...\n\n" + '\n'.join(tail)
    return result, True


def format_output(
    stdout: str,
    stderr: str,
    interrupted: bool = False,
    timeout: bool = False,
) -> str:
    """
    Format command output for display.

    Args:
        stdout: Standard output
        stderr: Standard error
        interrupted: Whether the command was interrupted
        timeout: Whether the command timed out

    Returns:
        Formatted output string
    """
    parts = []

    if stdout:
        truncated_stdout, was_truncated = truncate_output(stdout)
        parts.append(truncated_stdout)

    if stderr:
        truncated_stderr, _ = truncate_output(stderr)
        if truncated_stderr.strip():
            parts.append(f"\nSTDERR:\n{truncated_stderr}")

    if interrupted:
        parts.append('\n[Command was interrupted]')
    elif timeout:
        parts.append('\n[Command timed out]')

    return ''.join(parts) if parts else ''
