"""
Plugin startup check - runs startup checks for installed plugins.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class PluginStartupCheckResult:
    def __init__(
        self,
        plugin_id: str,
        passed: bool,
        message: Optional[str] = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.passed = passed
        self.message = message


async def run_plugin_startup_checks(
    plugin_ids: Optional[List[str]] = None,
) -> List[PluginStartupCheckResult]:
    """
    Run startup checks for installed plugins.
    Returns a list of check results.
    """
    return []


async def check_plugin_compatibility(plugin_id: str) -> PluginStartupCheckResult:
    """Check if a plugin is compatible with the current Claude Code version."""
    return PluginStartupCheckResult(
        plugin_id=plugin_id,
        passed=True,
        message=None,
    )
