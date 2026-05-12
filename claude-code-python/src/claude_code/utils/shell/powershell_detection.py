"""
powershell_detection.py - PowerShell detection utilities.

Port of TypeScript powershellDetection.ts.
"""

import os
import platform
import shutil
import subprocess
from typing import Optional


def is_powershell_available() -> bool:
    """
    Check if PowerShell is available on the current system.

    Returns:
        True if PowerShell (or pwsh) is available.
    """
    return bool(find_powershell_path())


def find_powershell_path() -> Optional[str]:
    """
    Find the path to PowerShell executable.

    Checks for pwsh (PowerShell Core) first, then powershell (Windows PowerShell).

    Returns:
        Path to PowerShell executable, or None if not found.
    """
    # Check environment override
    env_path = os.environ.get('CLAUDE_CODE_POWERSHELL_PATH')
    if env_path and os.path.isfile(env_path):
        return env_path

    # Check for pwsh (cross-platform PowerShell Core)
    pwsh = shutil.which('pwsh')
    if pwsh:
        return pwsh

    # Check for powershell (Windows PowerShell)
    if platform.system() == 'Windows':
        ps = shutil.which('powershell')
        if ps:
            return ps

        # Check common Windows paths
        windows_paths = [
            r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
            r'C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe',
        ]
        for path in windows_paths:
            if os.path.isfile(path):
                return path

    return None


def get_powershell_version() -> Optional[str]:
    """
    Get the PowerShell version.

    Returns:
        Version string like '7.4.0', or None if PowerShell not available.
    """
    ps_path = find_powershell_path()
    if not ps_path:
        return None

    try:
        result = subprocess.run(
            [ps_path, '-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


def is_powershell_preferred_shell() -> bool:
    """
    Check if PowerShell is the preferred shell based on environment.

    On Windows, PowerShell may be preferred over bash/zsh when
    no bash-compatible shell is available.

    Returns:
        True if PowerShell should be used as primary shell.
    """
    # Check explicit setting
    if os.environ.get('CLAUDE_CODE_USE_POWERSHELL', '').lower() in ('1', 'true', 'yes'):
        return True

    # On Windows, prefer PowerShell if bash is not available
    if platform.system() == 'Windows':
        bash = shutil.which('bash')
        if not bash and is_powershell_available():
            return True

    return False
