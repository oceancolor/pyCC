"""
Headless plugin install - installs plugins in headless/non-interactive mode.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


class PluginInstallResult:
    def __init__(
        self,
        success: bool,
        plugin_id: str,
        error: Optional[str] = None,
    ) -> None:
        self.success = success
        self.plugin_id = plugin_id
        self.error = error


async def headless_install_plugin(
    plugin_id: str,
    version: Optional[str] = None,
    marketplace_url: Optional[str] = None,
) -> PluginInstallResult:
    """
    Install a plugin in headless mode (no UI confirmation required).
    Used for automated/CI environments.
    """
    try:
        from .plugin_installation_helpers import install_plugin
        success, error = await install_plugin(
            plugin_id=plugin_id,
            version=version,
            marketplace_url=marketplace_url,
            headless=True,
        )
        return PluginInstallResult(
            success=success,
            plugin_id=plugin_id,
            error=error,
        )
    except Exception as e:
        return PluginInstallResult(
            success=False,
            plugin_id=plugin_id,
            error=str(e),
        )


async def headless_install_plugins(
    plugin_ids: List[str],
    marketplace_url: Optional[str] = None,
) -> List[PluginInstallResult]:
    """Install multiple plugins in headless mode."""
    results = []
    for pid in plugin_ids:
        result = await headless_install_plugin(pid, marketplace_url=marketplace_url)
        results.append(result)
    return results
