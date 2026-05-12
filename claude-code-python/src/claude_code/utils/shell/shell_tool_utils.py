"""
shell_tool_utils.py - Utility functions for shell tool results.

Port of TypeScript shellToolUtils.ts.
"""

import os
import re
from typing import Optional, Tuple


def format_shell_result(
    stdout: str,
    stderr: str,
    exit_code: int,
    command: str = '',
    new_cwd: Optional[str] = None,
    interrupted: bool = False,
) -> str:
    """
    Format shell command output for tool result.

    Args:
        stdout: Standard output
        stderr: Standard error
        exit_code: Exit code
        command: Original command (for context)
        new_cwd: New working directory after command
        interrupted: Whether the command was interrupted

    Returns:
        Formatted string for tool result.
    """
    from .output_limits import truncate_output

    parts = []

    if stdout:
        truncated_stdout, was_truncated = truncate_output(stdout)
        parts.append(truncated_stdout)
        if was_truncated:
            parts.append('\n[Output was truncated]')

    if stderr:
        truncated_stderr, _ = truncate_output(stderr)
        stderr_stripped = truncated_stderr.strip()
        if stderr_stripped:
            parts.append(f"\n<stderr>{stderr_stripped}</stderr>")

    if exit_code != 0 and not interrupted:
        parts.append(f"\nExit code: {exit_code}")

    if interrupted:
        parts.append('\n[Command interrupted]')

    return ''.join(parts)


def is_read_only_command(command: str) -> bool:
    """
    Determine if a command is read-only (safe to auto-approve).

    Args:
        command: Shell command to check

    Returns:
        True if the command is likely read-only.
    """
    READ_ONLY_COMMANDS = {
        'ls', 'cat', 'head', 'tail', 'grep', 'find', 'echo', 'pwd',
        'which', 'whoami', 'date', 'df', 'du', 'uname', 'env', 'printenv',
        'ps', 'top', 'uptime', 'id', 'groups', 'git log', 'git diff',
        'git status', 'git show', 'git branch', 'git remote', 'git fetch --dry-run',
        'wc', 'sort', 'uniq', 'awk', 'sed', 'cut', 'tr', 'nl', 'tee',
        'less', 'more', 'file', 'stat', 'readlink', 'dirname', 'basename',
        'diff', 'cmp',
    }

    first_token = command.strip().split()[0] if command.strip() else ''
    return first_token in READ_ONLY_COMMANDS


def parse_shell_tool_input(input_data: dict) -> Tuple[str, Optional[str]]:
    """
    Parse shell tool input parameters.

    Args:
        input_data: Dict with 'command' and optional 'restart' keys

    Returns:
        Tuple of (command, restart_hint)
    """
    command = input_data.get('command', '').strip()
    restart = input_data.get('restart')

    return command, str(restart) if restart else None


def get_cwd_display(cwd: str) -> str:
    """
    Get a display-friendly version of the working directory.

    Args:
        cwd: Current working directory

    Returns:
        Display string (may use ~ for home directory)
    """
    home = os.path.expanduser('~')
    if cwd.startswith(home):
        return '~' + cwd[len(home):]
    return cwd
