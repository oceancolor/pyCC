"""
Plugin directories - resolves plugin installation and storage directories.
"""

from __future__ import annotations

import os
from typing import Optional


def get_plugins_base_dir() -> str:
    """Get the base directory for all plugin installations."""
    return os.path.expanduser("~/.claude/plugins")


def get_plugin_repos_dir() -> str:
    """Get the directory where plugin repositories are stored."""
    return os.path.join(get_plugins_base_dir(), "repos")


def get_plugin_install_dir(plugin_id: str) -> str:
    """Get the installation directory for a specific plugin."""
    return os.path.join(get_plugin_repos_dir(), plugin_id)


def get_plugin_cache_dir() -> str:
    """Get the directory for plugin caches (zips, etc.)."""
    return os.path.join(get_plugins_base_dir(), "cache")


def ensure_plugin_dirs() -> None:
    """Ensure the plugin directories exist."""
    os.makedirs(get_plugin_repos_dir(), exist_ok=True)
    os.makedirs(get_plugin_cache_dir(), exist_ok=True)
