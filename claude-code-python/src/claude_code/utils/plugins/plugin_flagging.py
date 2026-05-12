"""
Plugin flagging - manages flagged/reported plugins.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class PluginFlag:
    def __init__(
        self,
        plugin_id: str,
        reason: str,
        severity: str = "warning",
    ) -> None:
        self.plugin_id = plugin_id
        self.reason = reason
        self.severity = severity  # 'warning' | 'error' | 'info'


_plugin_flags: Dict[str, PluginFlag] = {}


def flag_plugin(
    plugin_id: str,
    reason: str,
    severity: str = "warning",
) -> None:
    """Flag a plugin with a reason."""
    _plugin_flags[plugin_id] = PluginFlag(plugin_id, reason, severity)


def unflag_plugin(plugin_id: str) -> None:
    """Remove a flag from a plugin."""
    _plugin_flags.pop(plugin_id, None)


def get_plugin_flag(plugin_id: str) -> Optional[PluginFlag]:
    """Get the flag for a plugin, if any."""
    return _plugin_flags.get(plugin_id)


def is_plugin_flagged(plugin_id: str) -> bool:
    """Check if a plugin is flagged."""
    return plugin_id in _plugin_flags


def get_all_flagged_plugins() -> List[PluginFlag]:
    """Get all flagged plugins."""
    return list(_plugin_flags.values())
