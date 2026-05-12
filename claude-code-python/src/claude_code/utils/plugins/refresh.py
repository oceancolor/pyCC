"""
Refresh - refreshes plugin registry and installed plugin metadata.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


async def refresh_plugin_registry() -> Dict[str, Any]:
    """Refresh the plugin registry from the marketplace."""
    return {"plugins": [], "lastUpdated": None}


async def refresh_installed_plugins() -> List[Dict[str, Any]]:
    """Refresh metadata for installed plugins."""
    from .plugin_installation_helpers import get_installed_plugin_ids
    installed = get_installed_plugin_ids()
    return [{"id": pid, "status": "installed"} for pid in installed]


async def refresh_all() -> Dict[str, Any]:
    """Refresh both registry and installed plugins."""
    registry = await refresh_plugin_registry()
    installed = await refresh_installed_plugins()
    return {"registry": registry, "installed": installed}
