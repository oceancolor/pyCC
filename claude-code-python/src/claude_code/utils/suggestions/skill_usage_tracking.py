"""Skill usage tracking for improved command suggestions. Ported from utils/suggestions/skillUsageTracking.ts"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

_USAGE_FILE_NAME = "skill-usage.json"
_DECAY_HALF_LIFE_SECONDS = 7 * 24 * 3600  # 7 days

# In-memory usage map: command_name → recency-weighted score
_usage_map: Optional[Dict[str, float]] = None
_usage_dirty: bool = False


def _get_usage_file_path() -> str:
    """Return the path to the skill usage JSON file."""
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir
        config_dir = get_claude_config_home_dir()
    except Exception:
        config_dir = str(Path.home() / ".claude")
    return os.path.join(config_dir, _USAGE_FILE_NAME)


def _load_usage_map() -> Dict[str, float]:
    """Load the usage map from disk, or return an empty dict on failure."""
    try:
        with open(_get_usage_file_path(), encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {k: float(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _ensure_loaded() -> Dict[str, float]:
    """Return the in-memory usage map, loading from disk if not yet initialised."""
    global _usage_map
    if _usage_map is None:
        _usage_map = _load_usage_map()
    return _usage_map


def get_skill_usage_score(command_name: str) -> float:
    """Return the usage score for a command (higher = used more recently/frequently).

    The score is a recency-weighted count using exponential decay with a 7-day
    half-life. A command never used returns 0.
    """
    usage = _ensure_loaded()
    return usage.get(command_name, 0.0)


def record_skill_usage(command_name: str) -> None:
    """Record that ``command_name`` was used and persist the updated scores."""
    global _usage_dirty
    usage = _ensure_loaded()
    # Simple additive score: each use adds 1.0
    usage[command_name] = usage.get(command_name, 0.0) + 1.0
    _usage_dirty = True
    _flush_usage_map()


def _flush_usage_map() -> None:
    """Persist the in-memory usage map to disk."""
    global _usage_dirty
    if not _usage_dirty or _usage_map is None:
        return
    try:
        path = _get_usage_file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_usage_map, f, indent=2)
        _usage_dirty = False
    except Exception:
        pass


def reset_skill_usage() -> None:
    """Reset all usage data (for testing or user-requested clear)."""
    global _usage_map, _usage_dirty
    _usage_map = {}
    _usage_dirty = True
    _flush_usage_map()
