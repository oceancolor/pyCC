"""Plugins utilities sub-package. Ported from utils/plugins/.

Provides plugin discovery, installation management, marketplace integration,
and plugin lifecycle helpers for Claude Code extensions.
"""
from __future__ import annotations

from claude_code.utils.plugins.installed_plugins_manager import (
    clear_installed_plugins_cache,
    get_installed_plugins_file_path,
)
from claude_code.utils.plugins.marketplace_manager import (
    DeclaredMarketplace,
    LoadedPluginMarketplace,
)

__all__ = [
    "get_installed_plugins_file_path",
    "clear_installed_plugins_cache",
    "DeclaredMarketplace",
    "LoadedPluginMarketplace",
]
