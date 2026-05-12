"""
Plugin blocklist - manages blocked/banned plugins.
"""

from __future__ import annotations

from typing import List, Optional, Set

# Built-in blocked plugins (none in Python port)
BUILT_IN_BLOCKLIST: List[str] = []

_extra_blocked: Set[str] = set()


def is_plugin_blocked(plugin_id: str) -> bool:
    """Check if a plugin is blocked."""
    return plugin_id in BUILT_IN_BLOCKLIST or plugin_id in _extra_blocked


def get_blocked_plugins() -> List[str]:
    """Get the list of all blocked plugin IDs."""
    return list(set(BUILT_IN_BLOCKLIST) | _extra_blocked)


def add_to_blocklist(plugin_id: str) -> None:
    """Add a plugin to the runtime blocklist."""
    _extra_blocked.add(plugin_id)


def remove_from_blocklist(plugin_id: str) -> None:
    """Remove a plugin from the runtime blocklist."""
    _extra_blocked.discard(plugin_id)


def filter_blocked_plugins(plugins: List[str]) -> List[str]:
    """Filter out blocked plugins from a list."""
    return [p for p in plugins if not is_plugin_blocked(p)]
