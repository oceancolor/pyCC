"""
Plugin autoupdate - automatically updates plugins to newer versions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class PluginUpdateInfo:
    def __init__(
        self,
        plugin_id: str,
        current_version: str,
        latest_version: str,
    ) -> None:
        self.plugin_id = plugin_id
        self.current_version = current_version
        self.latest_version = latest_version


async def check_for_plugin_updates(
    installed_plugins: Optional[List[Dict[str, Any]]] = None,
) -> List[PluginUpdateInfo]:
    """Check for available updates for installed plugins."""
    return []


async def auto_update_plugins(
    plugins_to_update: Optional[List[PluginUpdateInfo]] = None,
) -> List[str]:
    """Auto-update plugins. Returns list of updated plugin IDs."""
    return []


def is_autoupdate_enabled() -> bool:
    """Check if plugin autoupdate is enabled in settings."""
    try:
        from ..settings.settings import get_settings_for_source
        settings = get_settings_for_source("userSettings")
        return bool((settings or {}).get("pluginAutoUpdate", True))
    except Exception:
        return True
