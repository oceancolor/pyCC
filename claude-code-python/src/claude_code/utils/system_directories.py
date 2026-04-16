"""System directory path constants.

Ported from systemDirectories.ts — cross-platform home/desktop/documents/downloads.
"""

import os
from pathlib import Path
from typing import Optional, TypedDict


class SystemDirectories(TypedDict, total=False):
    HOME: str
    DESKTOP: str
    DOCUMENTS: str
    DOWNLOADS: str


def get_system_directories(
    *,
    env: Optional[dict[str, Optional[str]]] = None,
    homedir: Optional[str] = None,
    platform: Optional[str] = None,
) -> SystemDirectories:
    """Get cross-platform system directories.

    Handles differences between Windows, macOS, Linux, and WSL.

    Args:
        env: Override for environment variables (default: os.environ).
        homedir: Override for home directory (default: Path.home()).
        platform: Override for platform string: 'windows', 'linux', 'wsl',
                  'macos', 'unknown' (default: auto-detected).
    """
    import sys

    if env is None:
        env = dict(os.environ)
    if homedir is None:
        homedir = str(Path.home())
    if platform is None:
        plat = sys.platform
        if plat == 'win32':
            platform = 'windows'
        elif plat == 'darwin':
            platform = 'macos'
        else:
            # Detect WSL
            uname = ''
            try:
                with open('/proc/version', 'r') as f:
                    uname = f.read().lower()
            except OSError:
                pass
            if 'microsoft' in uname or 'wsl' in uname:
                platform = 'wsl'
            else:
                platform = 'linux'

    home = homedir
    defaults: SystemDirectories = {
        'HOME': home,
        'DESKTOP': str(Path(home) / 'Desktop'),
        'DOCUMENTS': str(Path(home) / 'Documents'),
        'DOWNLOADS': str(Path(home) / 'Downloads'),
    }

    if platform == 'windows':
        user_profile = env.get('USERPROFILE') or home
        return {
            'HOME': home,
            'DESKTOP': str(Path(user_profile) / 'Desktop'),
            'DOCUMENTS': str(Path(user_profile) / 'Documents'),
            'DOWNLOADS': str(Path(user_profile) / 'Downloads'),
        }

    if platform in ('linux', 'wsl'):
        return {
            'HOME': home,
            'DESKTOP': env.get('XDG_DESKTOP_DIR') or defaults['DESKTOP'],
            'DOCUMENTS': env.get('XDG_DOCUMENTS_DIR') or defaults['DOCUMENTS'],
            'DOWNLOADS': env.get('XDG_DOWNLOAD_DIR') or defaults['DOWNLOADS'],
        }

    # macos + unknown
    return defaults
