"""
Orphaned plugin filter - filters out orphaned (no longer enabled) plugins.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def find_orphaned_plugins(
    installed_dirs: List[str],
    enabled_plugins: Optional[List[str]] = None,
) -> List[str]:
    """
    Find plugin directories that are orphaned (not in enabled list).
    Returns list of orphaned directory paths.
    """
    if enabled_plugins is None:
        return []

    enabled_set = set(enabled_plugins)
    orphaned = []
    for plugin_dir in installed_dirs:
        plugin_id = os.path.basename(plugin_dir)
        if plugin_id not in enabled_set:
            orphaned.append(plugin_dir)

    return orphaned


def filter_orphaned_plugins(
    plugins: List[Dict[str, Any]],
    enabled_plugins: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter out orphaned plugins from a list."""
    if enabled_plugins is None:
        return plugins

    enabled_set = set(enabled_plugins)
    return [p for p in plugins if p.get("id", p.get("pluginId", "")) in enabled_set]
