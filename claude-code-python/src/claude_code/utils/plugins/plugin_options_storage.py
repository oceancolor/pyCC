"""
Plugin options storage - stores per-plugin user preferences and options.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional


def get_plugin_options_file_path() -> str:
    """Get the path to the plugin options file."""
    return os.path.expanduser("~/.claude/plugin_options.json")


def load_all_plugin_options() -> Dict[str, Any]:
    """Load all plugin options from storage."""
    path = get_plugin_options_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_plugin_options(plugin_id: str) -> Dict[str, Any]:
    """Get stored options for a specific plugin."""
    all_options = load_all_plugin_options()
    return all_options.get(plugin_id) or {}


def set_plugin_option(plugin_id: str, key: str, value: Any) -> None:
    """Set an option for a specific plugin."""
    all_options = load_all_plugin_options()
    plugin_opts = all_options.setdefault(plugin_id, {})
    plugin_opts[key] = value
    path = get_plugin_options_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(all_options, f, indent=2)
    except Exception:
        pass


def clear_plugin_options(plugin_id: str) -> None:
    """Clear all options for a specific plugin."""
    all_options = load_all_plugin_options()
    all_options.pop(plugin_id, None)
    path = get_plugin_options_file_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(all_options, f, indent=2)
    except Exception:
        pass
