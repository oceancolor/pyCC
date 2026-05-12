"""
Load plugin output styles - loads output style definitions from installed plugins.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def load_plugin_output_styles(plugin_dir: str) -> List[Dict[str, Any]]:
    """Load output style definitions from a plugin directory."""
    styles: List[Dict[str, Any]] = []
    styles_file = os.path.join(plugin_dir, "output_styles.json")
    if os.path.exists(styles_file):
        try:
            with open(styles_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                styles.extend(data)
            elif isinstance(data, dict):
                styles.append(data)
        except Exception:
            pass
    return styles


def load_all_plugins_output_styles(
    plugin_dirs: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Load output styles from all installed plugin directories."""
    from .plugin_directories import get_plugin_repos_dir
    base = get_plugin_repos_dir()
    if not os.path.isdir(base):
        return []

    dirs = plugin_dirs or [
        os.path.join(base, d) for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    ]

    styles: List[Dict[str, Any]] = []
    for d in dirs:
        styles.extend(load_plugin_output_styles(d))
    return styles
