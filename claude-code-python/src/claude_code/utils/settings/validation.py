"""
Validation - validates settings files and returns errors.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple


class SettingsWithErrors:
    def __init__(self, settings: Dict[str, Any], errors: List[Any]) -> None:
        self.settings = settings
        self.errors = errors


def validate_settings(settings: Dict[str, Any]) -> List[str]:
    """Validate settings dict. Returns list of error messages."""
    errors = []

    # Validate permissions
    if "permissions" in settings:
        from .permission_validation import validate_permissions_list
        errors.extend(validate_permissions_list(settings.get("permissions")))

    # Validate model name format
    model = settings.get("model")
    if model is not None and not isinstance(model, str):
        errors.append("'model' must be a string")

    # Validate env
    env = settings.get("env")
    if env is not None and not isinstance(env, dict):
        errors.append("'env' must be an object")

    # Validate hooks
    hooks = settings.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        errors.append("'hooks' must be an object")

    return errors


def load_and_validate_settings_file(
    file_path: str,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Load a settings file and validate it. Returns (settings, errors)."""
    if not os.path.exists(file_path):
        return {}, []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"Invalid JSON in {file_path}: {e}"]
    except Exception as e:
        return None, [f"Could not read {file_path}: {e}"]

    if not isinstance(settings, dict):
        return None, [f"{file_path} must contain a JSON object"]

    errors = validate_settings(settings)
    return settings, errors


def get_settings_with_errors() -> SettingsWithErrors:
    """Get merged settings with all validation errors."""
    all_settings: Dict[str, Any] = {}
    all_errors: List[Any] = []

    try:
        from .settings import get_settings_file_path_for_source
        for source in ("userSettings", "projectSettings", "localSettings", "policySettings"):
            try:
                path = get_settings_file_path_for_source(source)
                if path:
                    settings, errors = load_and_validate_settings_file(path)
                    if settings:
                        all_settings.update(settings)
                    all_errors.extend(errors)
            except Exception:
                pass
    except Exception:
        pass

    return SettingsWithErrors(settings=all_settings, errors=all_errors)
