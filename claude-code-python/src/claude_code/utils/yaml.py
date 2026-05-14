"""YAML parsing wrapper. Ported from utils/yaml.ts.

Uses PyYAML under the hood.  The TypeScript version uses Bun.YAML when
running under Bun and falls back to the 'yaml' npm package otherwise.
In Python we always use PyYAML's safe API.
"""
from __future__ import annotations

from typing import Any, Iterator

import yaml as _yaml

__all__ = [
    "parse_yaml",
    "dump_yaml",
    "parse_yaml_all",
    "is_valid_yaml",
]


def parse_yaml(input_str: str) -> Any:
    """Parse a YAML string and return the Python object.

    Returns None for an empty or whitespace-only string (matches
    yaml.safe_load behaviour).
    """
    return _yaml.safe_load(input_str)


def dump_yaml(obj: Any, **kwargs: Any) -> str:
    """Serialise *obj* to a YAML string.

    Sensible defaults are applied (allow_unicode=True, sort_keys=False)
    but can be overridden via **kwargs.
    """
    defaults: dict[str, Any] = {
        "allow_unicode": True,
        "default_flow_style": False,
        "sort_keys": False,
    }
    defaults.update(kwargs)
    return _yaml.dump(obj, **defaults)


def parse_yaml_all(input_str: str) -> list[Any]:
    """Parse a multi-document YAML stream and return a list of objects."""
    return list(_yaml.safe_load_all(input_str))


def is_valid_yaml(input_str: str) -> bool:
    """Return True if *input_str* is syntactically valid YAML."""
    try:
        _yaml.safe_load(input_str)
        return True
    except _yaml.YAMLError:
        return False


def yaml_get(data: Any, path: str, default: Any = None) -> Any:
    """Retrieve a nested value from a parsed YAML structure by dot-separated path.

    Example::

        cfg = parse_yaml("a:\\n  b: 42")
        yaml_get(cfg, "a.b")  # → 42
    """
    parts = path.split(".")
    node = data
    for part in parts:
        if not isinstance(node, dict):
            return default
        node = node.get(part, default)
        if node is default:
            return default
    return node
