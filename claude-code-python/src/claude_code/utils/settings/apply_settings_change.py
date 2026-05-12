"""
Apply settings change - applies user-submitted settings changes to the config files.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple


def apply_settings_change(
    source: str,
    key: str,
    value: Any,
) -> Tuple[bool, Optional[str]]:
    """
    Apply a settings change to the appropriate config file.
    Returns (success, error_message).
    """
    try:
        from .settings import get_settings_file_path_for_source
        file_path = get_settings_file_path_for_source(source)
        if not file_path:
            return False, f"No settings file path found for source: {source}"

        # Load existing settings
        settings: Dict[str, Any] = {}
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                settings = json.load(f)

        # Apply the change using dot-notation for nested keys
        _set_nested(settings, key, value)

        # Write back
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)

        # Invalidate cache
        from .settings_cache import reset_settings_cache
        reset_settings_cache()

        return True, None
    except Exception as e:
        return False, str(e)


def _set_nested(obj: Dict[str, Any], key: str, value: Any) -> None:
    """Set a potentially nested key (dot-separated) in a dict."""
    parts = key.split(".")
    for part in parts[:-1]:
        obj = obj.setdefault(part, {})
    if value is None:
        obj.pop(parts[-1], None)
    else:
        obj[parts[-1]] = value
