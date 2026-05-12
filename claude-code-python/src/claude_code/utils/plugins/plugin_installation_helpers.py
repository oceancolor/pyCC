"""
Plugin installation helpers - helper functions for installing plugins.
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Optional, Tuple


async def install_plugin(
    plugin_id: str,
    version: Optional[str] = None,
    marketplace_url: Optional[str] = None,
    headless: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Install a plugin.
    Returns (success, error_message).
    """
    try:
        from .plugin_directories import get_plugin_install_dir, ensure_plugin_dirs
        install_dir = get_plugin_install_dir(plugin_id)

        if os.path.exists(install_dir):
            return True, None  # Already installed

        ensure_plugin_dirs()
        # In a real implementation, we'd download and extract the plugin here.
        # For the Python port stub, we just create the directory.
        os.makedirs(install_dir, exist_ok=True)

        return True, None
    except Exception as e:
        return False, str(e)


async def uninstall_plugin(plugin_id: str) -> Tuple[bool, Optional[str]]:
    """
    Uninstall a plugin.
    Returns (success, error_message).
    """
    try:
        from .plugin_directories import get_plugin_install_dir
        install_dir = get_plugin_install_dir(plugin_id)
        if os.path.exists(install_dir):
            shutil.rmtree(install_dir)
        return True, None
    except Exception as e:
        return False, str(e)


def is_plugin_installed(plugin_id: str) -> bool:
    """Check if a plugin is installed."""
    from .plugin_directories import get_plugin_install_dir
    return os.path.isdir(get_plugin_install_dir(plugin_id))


def get_installed_plugin_ids() -> List[str]:
    """Get list of installed plugin IDs."""
    from .plugin_directories import get_plugin_repos_dir
    repos_dir = get_plugin_repos_dir()
    if not os.path.isdir(repos_dir):
        return []
    return [
        d for d in os.listdir(repos_dir)
        if os.path.isdir(os.path.join(repos_dir, d))
    ]
