"""
prefix.py - Shell command prefix utilities.

Port of TypeScript utils/shell/prefix.ts.
"""

from typing import Optional


def get_shell_type() -> str:
    """
    Detect the current shell type from environment.

    Returns:
        'bash', 'zsh', 'powershell', or 'unknown'
    """
    import os

    shell = os.environ.get('SHELL', '')
    if 'zsh' in shell:
        return 'zsh'
    elif 'bash' in shell:
        return 'bash'
    elif 'fish' in shell:
        return 'fish'

    # Check CLAUDE_CODE_SHELL_TYPE override
    shell_type = os.environ.get('CLAUDE_CODE_SHELL_TYPE', '').lower()
    if shell_type in ('bash', 'zsh', 'powershell'):
        return shell_type

    return 'unknown'


def get_default_shell_prefix() -> Optional[str]:
    """
    Get the shell prefix from environment.

    Returns the CLAUDE_CODE_SHELL_PREFIX if set.
    """
    import os
    return os.environ.get('CLAUDE_CODE_SHELL_PREFIX') or None
