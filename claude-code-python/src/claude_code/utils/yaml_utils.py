"""YAML parsing wrapper. Ported from yaml.ts and yaml_utils.ts.

Uses PyYAML under the hood. safe_load / dump are the primary entry points.
"""
from __future__ import annotations

from typing import Any

import yaml as _yaml


def parse_yaml(input: str) -> Any:
    """Parse a YAML string and return the Python object.

    Equivalent to yaml.safe_load().  Returns None for an empty string.
    """
    return _yaml.safe_load(input)


def stringify_yaml(data: Any, **kwargs: Any) -> str:
    """Serialise *data* to a YAML string.

    Passes **kwargs directly to yaml.dump so callers can control indentation,
    default_flow_style, allow_unicode, etc.
    """
    defaults: dict[str, Any] = {
        "allow_unicode": True,
        "default_flow_style": False,
        "sort_keys": False,
    }
    defaults.update(kwargs)
    return _yaml.dump(data, **defaults)


def load_yaml_all(input: str) -> list[Any]:
    """Load all YAML documents from a multi-document stream."""
    return list(_yaml.safe_load_all(input))


def is_valid_yaml(input: str) -> bool:
    """Return True if *input* is valid YAML, False otherwise."""
    try:
        _yaml.safe_load(input)
        return True
    except _yaml.YAMLError:
        return False


def merge_yaml(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two dicts (override wins on conflicts)."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_yaml(result[key], value)
        else:
            result[key] = value
    return result
