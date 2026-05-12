"""
Load plugin hooks - loads hook definitions from installed plugins.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def load_plugin_hooks(plugin_dir: str) -> Dict[str, Any]:
    """Load hook definitions from a plugin directory."""
    hooks_file = os.path.join(plugin_dir, "hooks", "hooks.json")
    if not os.path.exists(hooks_file):
        return {}
    try:
        with open(hooks_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_all_plugins_hooks(
    plugin_dirs: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Load hooks from all installed plugin directories."""
    from .plugin_directories import get_plugin_repos_dir
    base = get_plugin_repos_dir()
    if not os.path.isdir(base):
        return []

    dirs = plugin_dirs or [
        os.path.join(base, d) for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    ]

    plugin_hooks: List[Dict[str, Any]] = []
    for d in dirs:
        hooks = load_plugin_hooks(d)
        if hooks:
            plugin_id = os.path.basename(d)
            plugin_hooks.append({"pluginId": plugin_id, "hooks": hooks, "pluginRoot": d})
    return plugin_hooks
