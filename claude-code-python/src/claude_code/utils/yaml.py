"""YAML parsing wrapper. Ported from utils/yaml.ts

Uses PyYAML (safe_load / dump). The TypeScript source used Bun.YAML when
running under Bun, otherwise the ``yaml`` npm package.
"""

from __future__ import annotations

from typing import Any, Iterator

import yaml as _yaml


def parse_yaml(input_str: str) -> Any:
    """Parse a YAML string and return the Python object.

    Returns None for an empty/whitespace string (same as yaml.safe_load).
    """
    return _yaml.safe_load(input_str)


def dump_yaml(obj: Any, **kwargs: Any) -> str:
    """Serialise *obj* to a YAML string.

    Keyword arguments are forwarded to :func:`yaml.dump` so callers can
    control indentation, flow style, etc.
    """
    defaults: dict[str, Any] = {
        "allow_unicode": True,
        "default_flow_style": False,
        "sort_keys": False,
    }
    defaults.update(kwargs)
    return _yaml.dump(obj, **defaults)


def load_yaml_all(input_str: str) -> list[Any]:
    """Load all YAML documents from a multi-document stream."""
    return list(_yaml.safe_load_all(input_str))


def is_valid_yaml(input_str: str) -> bool:
    """Return True if *input_str* is syntactically valid YAML."""
    try:
        _yaml.safe_load(input_str)
        return True
    except _yaml.YAMLError:
        return False


def deep_merge_yaml_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two dicts (override wins on key conflicts).

    This mirrors the common pattern of reading a YAML config file and
    layering user overrides on top.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_yaml_dicts(result[key], value)
        else:
            result[key] = value
    return result
