"""
Install counts - tracks plugin install counts.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional


def get_install_count_file_path() -> str:
    """Get the path to the install counts file."""
    return os.path.expanduser("~/.claude/plugin_install_counts.json")


def get_install_counts() -> Dict[str, int]:
    """Get the plugin install counts."""
    path = get_install_count_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: int(v) for k, v in data.items() if isinstance(v, (int, float))}
    except Exception:
        return {}


def increment_install_count(plugin_id: str) -> None:
    """Increment the install count for a plugin."""
    counts = get_install_counts()
    counts[plugin_id] = counts.get(plugin_id, 0) + 1
    path = get_install_count_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(counts, f)
    except Exception:
        pass


def get_install_count(plugin_id: str) -> int:
    """Get the install count for a plugin."""
    return get_install_counts().get(plugin_id, 0)
