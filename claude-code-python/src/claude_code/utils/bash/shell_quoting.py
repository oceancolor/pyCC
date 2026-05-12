"""
shell_quoting.py - Shell quoting and heredoc utilities.

Port of TypeScript shellQuoting.ts.
"""

import re
from .shell_quote import quote


def _contains_heredoc(command: str) -> bool:
    """Detects if a command contains a heredoc pattern."""
    # Check for bit-shift operators first
    if re.search(r'\d\s*<<\s*\d', command):
        return False
    if re.search(r'\[\[\s*\d+\s*<<\s*\d+\s*\]\]', command):
        return False
    if re.search(r'\$\(\(.*<<.*\)\)', command):
        return False

    heredoc_regex = re.compile(r"<<-?\s*(?:(['\"]?)(\w+)\1|\\(\w+))")
    return bool(heredoc_regex.search(command))


def _contains_multiline_string(command: str) -> bool:
    """Detects if a command contains multiline strings in quotes."""
    single_quote_multiline = re.compile(r"'(?:[^'\\]|\\.)*\n(?:[^'\\]|\\.)*'")
    double_quote_multiline = re.compile(r'"(?:[^"\\]|\\.)*\n(?:[^"\\]|\\.)*"')

    return bool(
        single_quote_multiline.search(command)
        or double_quote_multiline.search(command)
    )


def quote_shell_command(command: str, add_stdin_redirect: bool = True) -> str:
    """
    Quotes a shell command appropriately, preserving heredocs and multiline strings.

    Args:
        command: The command to quote
        add_stdin_redirect: Whether to add < /dev/null

    Returns:
        The properly quoted command
    """
    has_heredoc = _contains_heredoc(command)
    has_multiline = _contains_multiline_string(command)

    if has_heredoc or has_multiline:
        escaped = command.replace("'", "'\"'\"'")
        quoted = f"'{escaped}'"

        if has_heredoc:
            return quoted

        return f"{quoted} < /dev/null" if add_stdin_redirect else quoted

    if add_stdin_redirect:
        return quote([command, '<', '/dev/null'])

    return quote([command])


def has_stdin_redirect(command: str) -> bool:
    """
    Detects if a command already has a stdin redirect.
    Match patterns like: < file, </path/to/file, < /dev/null, etc.
    But not <<EOF (heredoc), << (bit shift), or <(process substitution)
    """
    return bool(re.search(r'(?:^|[\s;&|])<(?![<(])\s*\S+', command))


def should_add_stdin_redirect(command: str) -> bool:
    """
    Checks if stdin redirect should be added to a command.

    Returns:
        True if stdin redirect can be safely added
    """
    if _contains_heredoc(command):
        return False

    if has_stdin_redirect(command):
        return False

    return True


_NUL_REDIRECT_REGEX = re.compile(r'(\d?&?>+\s*)[Nn][Uu][Ll](?=\s|$|[|&;)\n])')


def rewrite_windows_null_redirect(command: str) -> str:
    """
    Rewrites Windows CMD-style `>nul` redirects to POSIX `/dev/null`.

    The model occasionally hallucinates Windows CMD syntax (e.g., `ls 2>nul`)
    even though our bash shell is always POSIX. When Git Bash sees `2>nul`,
    it creates a literal file named `nul` — a Windows reserved device name.
    """
    return _NUL_REDIRECT_REGEX.sub(r'\1/dev/null', command)
