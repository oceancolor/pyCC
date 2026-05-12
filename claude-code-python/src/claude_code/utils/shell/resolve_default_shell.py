"""
resolve_default_shell.py - Resolve the default shell for command execution.

Port of TypeScript resolveDefaultShell.ts.
"""

import os
import platform
import shutil
import subprocess
import sys
from typing import Optional


def resolve_default_shell() -> str:
    """
    Resolve the default shell for executing commands.

    Checks in this order:
    1. CLAUDE_CODE_SHELL environment variable
    2. SHELL environment variable (Unix)
    3. Common shell locations
    4. Falls back to /bin/sh

    Returns:
        Path to the shell executable.
    """
    # Check explicit override
    override = os.environ.get('CLAUDE_CODE_SHELL')
    if override and os.path.isfile(override):
        return override

    # On Unix/macOS, use SHELL environment variable
    if sys.platform != 'win32':
        shell = os.environ.get('SHELL')
        if shell and os.path.isfile(shell):
            return shell

        # Try common shell locations
        for candidate in ('/bin/zsh', '/usr/bin/zsh', '/bin/bash', '/usr/bin/bash', '/bin/sh'):
            if os.path.isfile(candidate):
                return candidate

        return '/bin/sh'

    # Windows: prefer Git Bash or WSL bash
    for candidate in (
        r'C:\Program Files\Git\bin\bash.exe',
        r'C:\Program Files (x86)\Git\bin\bash.exe',
    ):
        if os.path.isfile(candidate):
            return candidate

    # Try bash from PATH
    bash = shutil.which('bash')
    if bash:
        return bash

    # Try PowerShell
    from .powershell_detection import find_powershell_path
    ps_path = find_powershell_path()
    if ps_path:
        return ps_path

    return 'cmd.exe'


def get_shell_environment_overrides(shell_path: str) -> dict:
    """
    Get environment variable overrides needed for the given shell.

    Args:
        shell_path: Path to the shell

    Returns:
        Dict of environment variables to set
    """
    overrides = {}

    # Disable readline prompts in non-interactive mode
    overrides['TERM'] = os.environ.get('TERM', 'xterm-256color')

    # Disable bash history
    if 'bash' in shell_path:
        overrides['HISTFILE'] = ''
        overrides['HISTSIZE'] = '0'

    return overrides
