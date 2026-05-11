"""Background plugin and marketplace installation manager.
Ported from services/plugins/PluginInstallationManager.ts.
"""
from __future__ import annotations
import asyncio
from typing import Any, Callable, Dict, List, Literal, Optional, TypedDict


# ---------------------------------------------------------------------------
# Status types
# ---------------------------------------------------------------------------

MarketplaceStatus = Literal["pending", "installing", "installed", "failed"]
PluginStatus = Literal["pending", "installing", "installed", "failed"]


class MarketplaceInstallStatus(TypedDict):
    name: str
    status: MarketplaceStatus
    error: Optional[str]


class PluginInstallStatus(TypedDict):
    name: str
    status: PluginStatus
    error: Optional[str]


class InstallationStatus(TypedDict):
    marketplaces: List[MarketplaceInstallStatus]
    plugins: List[PluginInstallStatus]


# ---------------------------------------------------------------------------
# AppState update helper type
# ---------------------------------------------------------------------------

SetAppState = Callable[[Callable[[Any], Any]], None]


def _update_marketplace_status(
    set_app_state: SetAppState,
    name: str,
    status: MarketplaceStatus,
    error: Optional[str] = None,
) -> None:
    """Update a single marketplace's installation status in app state."""

    def _updater(prev: Any) -> Any:
        plugins = dict(getattr(prev, "plugins", {}) or {})
        installation_status = dict(plugins.get("installationStatus", {}))
        marketplaces: List[Dict[str, Any]] = list(
            installation_status.get("marketplaces", [])
        )
        updated = [
            {**m, "status": status, "error": error} if m.get("name") == name else m
            for m in marketplaces
        ]
        installation_status["marketplaces"] = updated
        plugins["installationStatus"] = installation_status

        # Return a new app state object / dict with plugins updated.
        if isinstance(prev, dict):
            return {**prev, "plugins": plugins}
        # If it's a dataclass / custom object, try to clone it.
        try:
            import dataclasses
            if dataclasses.is_dataclass(prev):
                return dataclasses.replace(prev, plugins=plugins)  # type: ignore[arg-type]
        except Exception:
            pass
        return prev

    set_app_state(_updater)


# ---------------------------------------------------------------------------
# Reconciler / refresh stubs — real implementations live in utils/plugins/
# ---------------------------------------------------------------------------

class _ReconcileResult(TypedDict):
    installed: List[str]
    updated: List[str]
    failed: List[str]
    up_to_date: List[str]


async def _get_declared_marketplaces() -> List[str]:
    """Return the list of marketplace names declared in config."""
    try:
        from claude_code.utils.plugins.marketplace_manager import (  # type: ignore[import]
            get_declared_marketplaces,
        )
        return get_declared_marketplaces()
    except ImportError:
        return []


async def _load_known_marketplaces_config() -> Dict[str, Any]:
    """Load the materialized marketplace config (already-installed state)."""
    try:
        from claude_code.utils.plugins.marketplace_manager import (  # type: ignore[import]
            load_known_marketplaces_config,
        )
        return await load_known_marketplaces_config()
    except (ImportError, Exception):
        return {}


async def _diff_marketplaces(
    declared: List[str], materialized: Dict[str, Any]
) -> Dict[str, Any]:
    """Return sets of marketplace names that are missing or source-changed."""
    try:
        from claude_code.utils.plugins.reconciler import diff_marketplaces  # type: ignore[import]
        return diff_marketplaces(declared, materialized)
    except ImportError:
        missing = [n for n in declared if n not in materialized]
        return {"missing": missing, "sourceChanged": []}


async def _reconcile_marketplaces(
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> _ReconcileResult:
    """Install / update marketplaces and return counts."""
    try:
        from claude_code.utils.plugins.reconciler import (  # type: ignore[import]
            reconcile_marketplaces,
        )
        return await reconcile_marketplaces(on_progress=on_progress)
    except ImportError:
        return {"installed": [], "updated": [], "failed": [], "up_to_date": []}


async def _refresh_active_plugins(set_app_state: SetAppState) -> None:
    """Clear caches and reload all active plugins."""
    try:
        from claude_code.utils.plugins.refresh import (  # type: ignore[import]
            refresh_active_plugins,
        )
        await refresh_active_plugins(set_app_state)
    except ImportError:
        pass


def _clear_marketplaces_cache() -> None:
    try:
        from claude_code.utils.plugins.marketplace_manager import (  # type: ignore[import]
            clear_marketplaces_cache,
        )
        clear_marketplaces_cache()
    except ImportError:
        pass


def _clear_plugin_cache(reason: str = "") -> None:
    try:
        from claude_code.utils.plugins.plugin_loader import (  # type: ignore[import]
            clear_plugin_cache,
        )
        clear_plugin_cache(reason)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------


async def perform_background_plugin_installations(
    set_app_state: SetAppState,
) -> None:
    """Perform background plugin startup checks and installations.

    Mirrors performBackgroundPluginInstallations() from the TypeScript source:
    1. Compute the diff between declared and already-installed marketplaces.
    2. Initialise app state with pending spinners for anything that needs work.
    3. Run reconcileMarketplaces(), mapping progress events to state updates.
    4. If new installs occurred → auto-refresh plugins.
    5. If only updates → set needsRefresh notification.

    Ported from services/plugins/PluginInstallationManager.ts.
    """
    try:
        declared = await _get_declared_marketplaces()
        materialized = await _load_known_marketplaces_config()
        diff = await _diff_marketplaces(declared, materialized)

        missing: List[str] = diff.get("missing", [])
        source_changed: List[str] = [c["name"] for c in diff.get("sourceChanged", [])]
        pending_names: List[str] = missing + source_changed

        # Initialise app state with pending status for each marketplace
        def _init_pending(prev: Any) -> Any:
            plugins = dict(getattr(prev, "plugins", {}) or {}) if not isinstance(prev, dict) else dict(prev.get("plugins", {}))
            plugins["installationStatus"] = {
                "marketplaces": [
                    {"name": n, "status": "pending", "error": None}
                    for n in pending_names
                ],
                "plugins": [],
            }
            if isinstance(prev, dict):
                return {**prev, "plugins": plugins}
            return prev

        set_app_state(_init_pending)

        if not pending_names:
            return

        def _on_progress(event: Dict[str, Any]) -> None:
            etype = event.get("type")
            name = event.get("name", "")
            if etype == "installing":
                _update_marketplace_status(set_app_state, name, "installing")
            elif etype == "installed":
                _update_marketplace_status(set_app_state, name, "installed")
            elif etype == "failed":
                _update_marketplace_status(
                    set_app_state, name, "failed", event.get("error")
                )

        result = await _reconcile_marketplaces(on_progress=_on_progress)

        if result["installed"]:
            # New marketplaces — auto-refresh plugins
            _clear_marketplaces_cache()
            try:
                await _refresh_active_plugins(set_app_state)
            except Exception:
                _clear_plugin_cache(
                    "perform_background_plugin_installations: auto-refresh failed"
                )

                def _set_needs_refresh(prev: Any) -> Any:
                    if isinstance(prev, dict):
                        plugins = dict(prev.get("plugins", {}))
                        if plugins.get("needsRefresh"):
                            return prev
                        plugins["needsRefresh"] = True
                        return {**prev, "plugins": plugins}
                    return prev

                set_app_state(_set_needs_refresh)

        elif result["updated"]:
            # Updates only — notify user to /reload-plugins
            _clear_marketplaces_cache()
            _clear_plugin_cache(
                "perform_background_plugin_installations: marketplaces reconciled"
            )

            def _set_needs_refresh_updates(prev: Any) -> Any:
                if isinstance(prev, dict):
                    plugins = dict(prev.get("plugins", {}))
                    if plugins.get("needsRefresh"):
                        return prev
                    plugins["needsRefresh"] = True
                    return {**prev, "plugins": plugins}
                return prev

            set_app_state(_set_needs_refresh_updates)

    except Exception:
        # Never crash the startup path
        pass
