"""
shell_prefix.py - Shell prefix command formatting.

Port of TypeScript shellPrefix.ts.
"""

from .shell_quote import quote


def format_shell_prefix_command(prefix: str, command: str) -> str:
    """
    Parses a shell prefix that may contain an executable path and arguments.

    Examples:
    - "bash" -> quotes as 'bash'
    - "/usr/bin/bash -c" -> quotes as '/usr/bin/bash' -c
    - "C:\\Program Files\\Git\\bin\\bash.exe -c" -> quotes as quoted path + args

    Args:
        prefix: The shell prefix string containing executable and optional arguments
        command: The command to be executed

    Returns:
        The properly formatted command string with quoted components
    """
    # Split on the last space before a dash to separate executable from arguments
    space_before_dash = prefix.rfind(' -')
    if space_before_dash > 0:
        exec_path = prefix[:space_before_dash]
        args = prefix[space_before_dash + 1:]
        return f"{quote([exec_path])} {args} {quote([command])}"
    else:
        return f"{quote([prefix])} {quote([command])}"
