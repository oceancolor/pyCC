"""
Validate plugin - validates a plugin's structure and manifest.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple


def validate_plugin_manifest(manifest: Any) -> Tuple[bool, List[str]]:
    """Validate a plugin manifest. Returns (is_valid, errors)."""
    errors: List[str] = []

    if not isinstance(manifest, dict):
        return False, ["Manifest must be a JSON object"]

    if not manifest.get("name"):
        errors.append("Manifest is missing required field 'name'")

    if not manifest.get("version"):
        errors.append("Manifest is missing required field 'version'")

    if not isinstance(manifest.get("name", ""), str):
        errors.append("'name' must be a string")

    return len(errors) == 0, errors


def validate_plugin_directory(plugin_dir: str) -> Tuple[bool, List[str]]:
    """Validate a plugin directory structure."""
    errors: List[str] = []

    if not os.path.isdir(plugin_dir):
        return False, [f"Plugin directory does not exist: {plugin_dir}"]

    # Check for manifest file
    manifest_path = os.path.join(plugin_dir, "manifest.json")
    package_path = os.path.join(plugin_dir, "package.json")

    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            valid, manifest_errors = validate_plugin_manifest(manifest)
            errors.extend(manifest_errors)
        except Exception as e:
            errors.append(f"Could not read manifest.json: {e}")
    elif os.path.exists(package_path):
        try:
            with open(package_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            # package.json needs at least name and version
            if not pkg.get("name"):
                errors.append("package.json is missing 'name'")
        except Exception as e:
            errors.append(f"Could not read package.json: {e}")
    else:
        errors.append("Plugin is missing manifest.json or package.json")

    return len(errors) == 0, errors
