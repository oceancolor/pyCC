"""
Add dir plugin settings - reads plugin-related settings from a directory.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def read_dir_plugin_settings(directory: str) -> Dict[str, Any]:
    """
    Read plugin-related settings from a settings.json file in the given directory.
    Returns the 'plugins' section or an empty dict.
    """
    settings_path = os.path.join(directory, ".claude", "settings.json")
    if not os.path.exists(settings_path):
        settings_path = os.path.join(directory, "settings.json")

    if not os.path.exists(settings_path):
        return {}

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data.get("plugins") or {}
    except Exception:
        return {}


def get_dir_plugin_extra_marketplaces(directory: str) -> List[str]:
    """Get extra known marketplaces from directory settings."""
    settings = read_dir_plugin_settings(directory)
    return settings.get("extraKnownMarketplaces") or []


def get_dir_enabled_plugins(directory: str) -> Optional[List[str]]:
    """Get enabled plugins from directory settings."""
    settings = read_dir_plugin_settings(directory)
    return settings.get("enabledPlugins")
