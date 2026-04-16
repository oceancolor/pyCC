"""
Core plugin operations (install, uninstall, enable, disable, update).

Ported from services/plugins/pluginOperations.ts (1088 lines).

This module provides pure library functions that can be used by both:
- CLI commands (claude plugin install/uninstall/enable/disable/update)
- Interactive UI

Functions in this module:
- Do NOT call sys.exit()
- Do NOT write to console
- Return result objects indicating success/failure with messages
- Can raise errors for unexpected failures
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

# Valid installable scopes (excludes 'managed' which can only be installed
# from managed-settings.json)
VALID_INSTALLABLE_SCOPES: Tuple[str, ...] = ("user", "project", "local")

# Valid scopes for update operations (includes 'managed')
VALID_UPDATE_SCOPES: Tuple[str, ...] = ("user", "project", "local", "managed")

# Type aliases
InstallableScope = str   # 'user' | 'project' | 'local'
PluginScope = str        # 'user' | 'project' | 'local' | 'managed'


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class PluginOperationResult:
    """Result of a plugin operation."""

    def __init__(
        self,
        success: bool,
        message: str,
        plugin_id: Optional[str] = None,
        plugin_name: Optional[str] = None,
        scope: Optional[PluginScope] = None,
        reverse_dependents: Optional[List[str]] = None,
    ) -> None:
        self.success = success
        self.message = message
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.scope = scope
        self.reverse_dependents = reverse_dependents

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"success": self.success, "message": self.message}
        if self.plugin_id is not None:
            d["plugin_id"] = self.plugin_id
        if self.plugin_name is not None:
            d["plugin_name"] = self.plugin_name
        if self.scope is not None:
            d["scope"] = self.scope
        if self.reverse_dependents is not None:
            d["reverse_dependents"] = self.reverse_dependents
        return d

    def __repr__(self) -> str:
        return f"PluginOperationResult(success={self.success}, message={self.message!r})"


class PluginUpdateResult:
    """Result of a plugin update operation."""

    def __init__(
        self,
        success: bool,
        message: str,
        plugin_id: Optional[str] = None,
        new_version: Optional[str] = None,
        old_version: Optional[str] = None,
        already_up_to_date: Optional[bool] = None,
        scope: Optional[PluginScope] = None,
    ) -> None:
        self.success = success
        self.message = message
        self.plugin_id = plugin_id
        self.new_version = new_version
        self.old_version = old_version
        self.already_up_to_date = already_up_to_date
        self.scope = scope

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"success": self.success, "message": self.message}
        if self.plugin_id is not None:
            d["plugin_id"] = self.plugin_id
        if self.new_version is not None:
            d["new_version"] = self.new_version
        if self.old_version is not None:
            d["old_version"] = self.old_version
        if self.already_up_to_date is not None:
            d["already_up_to_date"] = self.already_up_to_date
        if self.scope is not None:
            d["scope"] = self.scope
        return d

    def __repr__(self) -> str:
        return f"PluginUpdateResult(success={self.success}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------

def assert_installable_scope(scope: str) -> None:
    """Assert that a scope is a valid installable scope at runtime."""
    if scope not in VALID_INSTALLABLE_SCOPES:
        raise ValueError(
            f'Invalid scope "{scope}". Must be one of: {", ".join(VALID_INSTALLABLE_SCOPES)}'
        )


def is_installable_scope(scope: PluginScope) -> bool:
    """Type guard to check if a scope is an installable scope (not 'managed')."""
    return scope in VALID_INSTALLABLE_SCOPES


def get_project_path_for_scope(scope: PluginScope) -> Optional[str]:
    """
    Get the project path for scopes that are project-specific.
    Returns the original cwd for 'project' and 'local' scopes, undefined otherwise.
    """
    if scope in ("project", "local"):
        try:
            from ...bootstrap.state import get_original_cwd
            return get_original_cwd()
        except (ImportError, Exception):
            return os.getcwd()
    return None


def _scope_to_setting_source(scope: InstallableScope) -> str:
    """Convert a plugin scope to a settings source key."""
    mapping = {
        "user": "userSettings",
        "project": "projectSettings",
        "local": "localSettings",
    }
    return mapping.get(scope, "userSettings")


def _parse_plugin_identifier(plugin: str) -> Dict[str, Optional[str]]:
    """
    Parse a plugin identifier into name and marketplace components.
    'name@marketplace' → {'name': 'name', 'marketplace': 'marketplace'}
    'name' → {'name': 'name', 'marketplace': None}
    """
    if "@" in plugin:
        parts = plugin.split("@", 1)
        return {"name": parts[0], "marketplace": parts[1]}
    return {"name": plugin, "marketplace": None}


# ---------------------------------------------------------------------------
# Settings helpers (stubs for missing settings module)
# ---------------------------------------------------------------------------

def _get_settings_for_source(source: str) -> Optional[Dict[str, Any]]:
    """Get settings for a given source."""
    try:
        from ...utils.settings.settings import get_settings_for_source
        return get_settings_for_source(source)
    except (ImportError, AttributeError, Exception):
        return None


def _update_settings_for_source(source: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update settings for a given source. Returns dict with optional 'error' key."""
    try:
        from ...utils.settings.settings import update_settings_for_source
        result = update_settings_for_source(source, updates)
        return result if isinstance(result, dict) else {}
    except (ImportError, AttributeError, Exception) as e:
        return {"error": e}


def _clear_all_caches() -> None:
    """Clear all plugin caches."""
    try:
        from ...utils.plugins.cache_utils import clear_all_caches
        clear_all_caches()
    except (ImportError, Exception):
        pass


def _get_plugin_editable_scopes() -> Dict[str, Any]:
    """Get the set of currently enabled plugins across editable scopes."""
    try:
        from ...utils.plugins.plugin_startup_check import get_plugin_editable_scopes
        result = get_plugin_editable_scopes()
        return result if isinstance(result, dict) else {}
    except (ImportError, Exception):
        return {}


def _is_builtin_plugin_id(plugin: str) -> bool:
    """Check if a plugin ID refers to a built-in plugin."""
    try:
        from ...plugins.builtin_plugins import is_builtin_plugin_id
        return is_builtin_plugin_id(plugin)
    except (ImportError, Exception):
        return False


def _is_plugin_blocked_by_policy(plugin_id: str) -> bool:
    """Check if a plugin is blocked by organizational policy."""
    try:
        from ...utils.plugins.plugin_policy import is_plugin_blocked_by_policy
        return is_plugin_blocked_by_policy(plugin_id)
    except (ImportError, Exception):
        return False


def _find_reverse_dependents(plugin_id: str, all_plugins: List[Any]) -> List[str]:
    """Find plugins that declare this plugin as a dependency."""
    try:
        from ...utils.plugins.dependency_resolver import find_reverse_dependents
        result = find_reverse_dependents(plugin_id, all_plugins)
        return result if isinstance(result, list) else []
    except (ImportError, Exception):
        return []


def _format_reverse_dependents_suffix(dependents: List[str]) -> str:
    """Format a suffix warning about reverse dependents."""
    if not dependents:
        return ""
    try:
        from ...utils.plugins.dependency_resolver import format_reverse_dependents_suffix
        return format_reverse_dependents_suffix(dependents)
    except (ImportError, Exception):
        if len(dependents) == 1:
            return f" (warning: {dependents[0]} depends on this plugin)"
        return f" (warning: {len(dependents)} plugins depend on this plugin)"


def _mark_plugin_version_orphaned(install_path: str) -> None:
    """Mark a plugin version as orphaned for cleanup."""
    try:
        from ...utils.plugins.cache_utils import mark_plugin_version_orphaned
        import asyncio
        coro = mark_plugin_version_orphaned(install_path)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(coro)
            else:
                loop.run_until_complete(coro)
        except Exception:
            pass
    except (ImportError, Exception):
        pass


def _delete_plugin_options(plugin_id: str) -> None:
    """Delete stored plugin options."""
    try:
        from ...utils.plugins.plugin_options_storage import delete_plugin_options
        delete_plugin_options(plugin_id)
    except (ImportError, Exception):
        pass


async def _delete_plugin_data_dir(plugin_id: str) -> None:
    """Delete the plugin data directory."""
    try:
        from ...utils.plugins.plugin_directories import delete_plugin_data_dir
        await delete_plugin_data_dir(plugin_id)
    except (ImportError, Exception):
        pass


async def _load_all_plugins() -> Dict[str, List[Any]]:
    """Load all plugins, returning {'enabled': [...], 'disabled': [...]}."""
    try:
        from ...utils.plugins.plugin_loader import load_all_plugins
        result = await load_all_plugins()
        return result if isinstance(result, dict) else {"enabled": [], "disabled": []}
    except (ImportError, Exception):
        return {"enabled": [], "disabled": []}


async def _install_resolved_plugin(params: Dict[str, Any]) -> Dict[str, Any]:
    """Install a resolved plugin from marketplace entry."""
    try:
        from ...utils.plugins.plugin_installation_helpers import install_resolved_plugin
        return await install_resolved_plugin(params)
    except (ImportError, Exception) as e:
        return {"ok": False, "reason": "resolution-failed", "message": str(e)}


def _format_resolution_error(resolution: Any) -> str:
    """Format a resolution error for display."""
    try:
        from ...utils.plugins.plugin_installation_helpers import format_resolution_error
        return format_resolution_error(resolution)
    except (ImportError, Exception):
        return str(resolution)


# ---------------------------------------------------------------------------
# Helper: find plugin in settings
# ---------------------------------------------------------------------------

def is_plugin_enabled_at_project_scope(plugin_id: str) -> bool:
    """
    Is this plugin enabled (value === True) in .claude/settings.json?

    Distinct from V2 installed_plugins.json scope: that file tracks where a
    plugin was *installed from*, but the same plugin can also be enabled at
    project scope via settings.
    """
    settings = _get_settings_for_source("projectSettings")
    if settings and isinstance(settings.get("enabledPlugins"), dict):
        return settings["enabledPlugins"].get(plugin_id) is True
    return False


def _find_plugin_in_settings(plugin: str) -> Optional[Dict[str, str]]:
    """
    Search all editable settings scopes for a plugin ID matching the given input.

    Returns {'plugin_id': ..., 'scope': ...} or None.
    Precedence: local > project > user (most specific wins).
    """
    has_marketplace = "@" in plugin
    search_order: List[InstallableScope] = ["local", "project", "user"]

    for scope in search_order:
        source = _scope_to_setting_source(scope)
        settings = _get_settings_for_source(source)
        if not settings:
            continue
        enabled_plugins = settings.get("enabledPlugins", {})
        if not isinstance(enabled_plugins, dict):
            continue
        for key in enabled_plugins:
            if has_marketplace:
                if key == plugin:
                    return {"plugin_id": key, "scope": scope}
            else:
                if key == plugin or key.startswith(f"{plugin}@"):
                    return {"plugin_id": key, "scope": scope}
    return None


# ---------------------------------------------------------------------------
# Helper: find plugin from loaded plugins list
# ---------------------------------------------------------------------------

def _find_plugin_by_identifier(plugin: str, plugins: List[Any]) -> Optional[Any]:
    """Find a plugin from loaded plugins by name or identifier."""
    parsed = _parse_plugin_identifier(plugin)
    name = parsed["name"]
    marketplace = parsed["marketplace"]

    for p in plugins:
        p_name = getattr(p, "name", None) or (p.get("name") if isinstance(p, dict) else None)
        if p_name == plugin or p_name == name:
            return p
        if marketplace:
            p_source = getattr(p, "source", None) or (p.get("source") if isinstance(p, dict) else None)
            if p_name == name and p_source and f"@{marketplace}" in str(p_source):
                return p
    return None


def _resolve_delisted_plugin_id(plugin: str) -> Optional[Dict[str, str]]:
    """
    Resolve a plugin ID from V2 installed plugins data for a plugin that may
    have been delisted from its marketplace.
    """
    from .installed_plugins_manager import load_installed_plugins_v2

    parsed = _parse_plugin_identifier(plugin)
    name = parsed["name"]
    installed_data = load_installed_plugins_v2()

    if plugin in installed_data.plugins and installed_data.plugins[plugin]:
        return {"plugin_id": plugin, "plugin_name": name or plugin}

    matching_key = next(
        (
            key
            for key in installed_data.plugins
            if _parse_plugin_identifier(key)["name"] == name
            and installed_data.plugins[key]
        ),
        None,
    )
    if matching_key:
        return {"plugin_id": matching_key, "plugin_name": name or plugin}
    return None


def get_plugin_installation_from_v2(plugin_id: str) -> Dict[str, Any]:
    """
    Get the most relevant installation for a plugin from V2 data.

    Priority order: local (matching project) > project (matching project) > user > first available.
    """
    from .installed_plugins_manager import load_installed_plugins_v2

    installed_data = load_installed_plugins_v2()
    installations = installed_data.plugins.get(plugin_id)

    if not installations:
        return {"scope": "user"}

    try:
        from ...bootstrap.state import get_original_cwd
        current_project_path = get_original_cwd()
    except (ImportError, Exception):
        current_project_path = os.getcwd()

    # Priority: local > project > user > managed
    local_install = next(
        (i for i in installations if i.scope == "local" and i.project_path == current_project_path),
        None,
    )
    if local_install:
        return {"scope": local_install.scope, "project_path": local_install.project_path}

    project_install = next(
        (
            i
            for i in installations
            if i.scope == "project" and i.project_path == current_project_path
        ),
        None,
    )
    if project_install:
        return {"scope": project_install.scope, "project_path": project_install.project_path}

    user_install = next((i for i in installations if i.scope == "user"), None)
    if user_install:
        return {"scope": user_install.scope}

    # Fall back to first installation
    return {
        "scope": installations[0].scope,
        "project_path": installations[0].project_path,
    }


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

async def install_plugin_op(
    plugin: str,
    scope: InstallableScope = "user",
) -> PluginOperationResult:
    """
    Install a plugin (settings-first).

    Order of operations:
      1. Search materialized marketplaces for the plugin
      2. Write settings (THE ACTION — declares intent)
      3. Cache plugin + record version hint (materialization)

    :param plugin: Plugin identifier (name or plugin@marketplace)
    :param scope: Installation scope: user, project, or local (defaults to 'user')
    :returns: Result indicating success/failure
    """
    assert_installable_scope(scope)

    parsed = _parse_plugin_identifier(plugin)
    plugin_name = parsed["name"]
    marketplace_name = parsed["marketplace"]

    found_plugin: Optional[Any] = None
    found_marketplace: Optional[str] = None
    marketplace_install_location: Optional[str] = None

    try:
        from .marketplace_manager import get_plugin_by_id, get_marketplace, load_known_marketplaces_config

        if marketplace_name:
            plugin_info = await get_plugin_by_id(plugin)
            if plugin_info:
                found_plugin = plugin_info.get("entry")
                found_marketplace = marketplace_name
                marketplace_install_location = plugin_info.get("marketplace_install_location")
        else:
            marketplaces = await load_known_marketplaces_config()
            for mkt_name, mkt_config in marketplaces.items():
                try:
                    marketplace_obj = await get_marketplace(mkt_name)
                    plugins_list = (
                        marketplace_obj.plugins
                        if hasattr(marketplace_obj, "plugins")
                        else marketplace_obj.get("plugins", [])
                    )
                    for p in plugins_list:
                        p_name = getattr(p, "name", None) or (p.get("name") if isinstance(p, dict) else None)
                        if p_name == plugin_name:
                            found_plugin = p
                            found_marketplace = mkt_name
                            marketplace_install_location = (
                                mkt_config.install_location
                                if hasattr(mkt_config, "install_location")
                                else mkt_config.get("install_location", "")
                            )
                            break
                    if found_plugin:
                        break
                except Exception as e:
                    logger.error("Error loading marketplace %s: %s", mkt_name, e)
                    continue
    except (ImportError, Exception) as e:
        logger.debug("Marketplace lookup failed: %s", e)

    if not found_plugin or not found_marketplace:
        location = f'marketplace "{marketplace_name}"' if marketplace_name else "any configured marketplace"
        return PluginOperationResult(
            success=False,
            message=f'Plugin "{plugin_name}" not found in {location}',
        )

    entry = found_plugin
    entry_name = getattr(entry, "name", None) or (entry.get("name") if isinstance(entry, dict) else plugin_name)
    plugin_id = f"{entry_name}@{found_marketplace}"

    result = await _install_resolved_plugin(
        {
            "plugin_id": plugin_id,
            "entry": entry,
            "scope": scope,
            "marketplace_install_location": marketplace_install_location,
        }
    )

    if not result.get("ok", False):
        reason = result.get("reason", "unknown")
        dep_name = result.get("plugin_name", plugin_name)
        blocked_dep = result.get("blocked_dependency")

        if reason == "local-source-no-location":
            return PluginOperationResult(
                success=False,
                message=f'Cannot install local plugin "{dep_name}" without marketplace install location',
            )
        elif reason == "settings-write-failed":
            return PluginOperationResult(
                success=False,
                message=f'Failed to update settings: {result.get("message", "")}',
            )
        elif reason == "resolution-failed":
            return PluginOperationResult(
                success=False,
                message=_format_resolution_error(result.get("resolution")),
            )
        elif reason == "blocked-by-policy":
            return PluginOperationResult(
                success=False,
                message=f'Plugin "{dep_name}" is blocked by your organization\'s policy and cannot be installed',
            )
        elif reason == "dependency-blocked-by-policy":
            return PluginOperationResult(
                success=False,
                message=f'Plugin "{dep_name}" depends on "{blocked_dep}", which is blocked by your organization\'s policy',
            )
        else:
            return PluginOperationResult(
                success=False,
                message=result.get("message", f'Failed to install plugin "{plugin_name}"'),
            )

    dep_note = result.get("dep_note", "")
    return PluginOperationResult(
        success=True,
        message=f"Successfully installed plugin: {plugin_id} (scope: {scope}){dep_note}",
        plugin_id=plugin_id,
        plugin_name=entry_name,
        scope=scope,
    )


async def uninstall_plugin_op(
    plugin: str,
    scope: InstallableScope = "user",
    delete_data_dir: bool = True,
) -> PluginOperationResult:
    """
    Uninstall a plugin.

    :param plugin: Plugin name or plugin@marketplace identifier
    :param scope: Uninstall from scope: user, project, or local (defaults to 'user')
    :param delete_data_dir: Whether to delete the plugin data directory
    :returns: Result indicating success/failure
    """
    assert_installable_scope(scope)

    from .installed_plugins_manager import (
        load_installed_plugins_v2,
        remove_plugin_installation,
    )

    loaded = await _load_all_plugins()
    all_plugins = loaded.get("enabled", []) + loaded.get("disabled", [])

    found_plugin = _find_plugin_by_identifier(plugin, all_plugins)

    setting_source = _scope_to_setting_source(scope)
    settings = _get_settings_for_source(setting_source)

    plugin_id: str
    plugin_name_str: str

    if found_plugin:
        fp_name = getattr(found_plugin, "name", None) or (
            found_plugin.get("name") if isinstance(found_plugin, dict) else None
        ) or plugin
        enabled_plugins = settings.get("enabledPlugins", {}) if settings else {}
        plugin_id = next(
            (
                k
                for k in enabled_plugins
                if k == plugin or k == fp_name or k.startswith(f"{fp_name}@")
            ),
            plugin if "@" in plugin else fp_name,
        )
        plugin_name_str = fp_name
    else:
        resolved = _resolve_delisted_plugin_id(plugin)
        if not resolved:
            return PluginOperationResult(
                success=False,
                message=f'Plugin "{plugin}" not found in installed plugins',
            )
        plugin_id = resolved["plugin_id"]
        plugin_name_str = resolved["plugin_name"]

    project_path = get_project_path_for_scope(scope)
    installed_data = load_installed_plugins_v2()
    installations = installed_data.plugins.get(plugin_id)
    scope_installation = next(
        (
            i
            for i in (installations or [])
            if i.scope == scope and i.project_path == project_path
        ),
        None,
    )

    if not scope_installation:
        installation_info = get_plugin_installation_from_v2(plugin_id)
        actual_scope = installation_info.get("scope", "user")
        if actual_scope != scope and installations:
            if actual_scope == "project":
                return PluginOperationResult(
                    success=False,
                    message=(
                        f'Plugin "{plugin}" is enabled at project scope (.claude/settings.json, '
                        f"shared with your team). To disable just for you: "
                        f"claude plugin disable {plugin} --scope local"
                    ),
                )
            return PluginOperationResult(
                success=False,
                message=(
                    f'Plugin "{plugin}" is installed in {actual_scope} scope, not {scope}. '
                    f"Use --scope {actual_scope} to uninstall."
                ),
            )
        return PluginOperationResult(
            success=False,
            message=f'Plugin "{plugin}" is not installed in {scope} scope. Use --scope to specify the correct scope.',
        )

    install_path = scope_installation.install_path

    # Remove from settings
    new_enabled_plugins = dict((settings or {}).get("enabledPlugins", {}))
    new_enabled_plugins[plugin_id] = None  # signal deletion
    _update_settings_for_source(setting_source, {"enabledPlugins": new_enabled_plugins})
    _clear_all_caches()

    # Remove from installed_plugins_v2.json for this scope
    remove_plugin_installation(plugin_id, scope, project_path)

    updated_data = load_installed_plugins_v2()
    remaining_installations = updated_data.plugins.get(plugin_id)
    is_last_scope = not remaining_installations

    if is_last_scope and install_path:
        _mark_plugin_version_orphaned(install_path)

    if is_last_scope:
        _delete_plugin_options(plugin_id)
        if delete_data_dir:
            await _delete_plugin_data_dir(plugin_id)

    reverse_dependents = _find_reverse_dependents(plugin_id, all_plugins)
    dep_warn = _format_reverse_dependents_suffix(reverse_dependents)

    return PluginOperationResult(
        success=True,
        message=f"Successfully uninstalled plugin: {plugin_name_str} (scope: {scope}){dep_warn}",
        plugin_id=plugin_id,
        plugin_name=plugin_name_str,
        scope=scope,
        reverse_dependents=reverse_dependents if reverse_dependents else None,
    )


async def set_plugin_enabled_op(
    plugin: str,
    enabled: bool,
    scope: Optional[InstallableScope] = None,
) -> PluginOperationResult:
    """
    Set plugin enabled/disabled status (settings-first).

    Resolves the plugin ID and scope from settings — does NOT pre-gate on
    installed_plugins.json. Settings declares intent; if the plugin isn't
    cached yet, the next load will cache it.

    :param plugin: Plugin name or plugin@marketplace identifier
    :param enabled: True to enable, False to disable
    :param scope: Optional scope. If not provided, auto-detects most specific scope.
    :returns: Result indicating success/failure
    """
    operation = "enable" if enabled else "disable"

    # Built-in plugins: always use user-scope settings
    if _is_builtin_plugin_id(plugin):
        current_settings = _get_settings_for_source("userSettings")
        current_enabled_plugins = {}
        if current_settings:
            current_enabled_plugins = dict(current_settings.get("enabledPlugins", {}))
        current_enabled_plugins[plugin] = enabled
        result = _update_settings_for_source(
            "userSettings",
            {"enabledPlugins": current_enabled_plugins},
        )
        if result.get("error"):
            return PluginOperationResult(
                success=False,
                message=f"Failed to {operation} built-in plugin: {result['error']}",
            )
        _clear_all_caches()
        parsed = _parse_plugin_identifier(plugin)
        return PluginOperationResult(
            success=True,
            message=f"Successfully {operation}d built-in plugin: {parsed['name']}",
            plugin_id=plugin,
            plugin_name=parsed["name"],
            scope="user",
        )

    if scope is not None:
        assert_installable_scope(scope)

    # Resolve plugin_id and scope from settings
    plugin_id: str
    resolved_scope: InstallableScope

    found = _find_plugin_in_settings(plugin)

    SCOPE_PRECEDENCE: Dict[str, int] = {"user": 0, "project": 1, "local": 2}

    if scope is not None:
        resolved_scope = scope
        if found:
            plugin_id = found["plugin_id"]
        elif "@" in plugin:
            plugin_id = plugin
        else:
            return PluginOperationResult(
                success=False,
                message=f'Plugin "{plugin}" not found in settings. Use plugin@marketplace format.',
            )
    elif found:
        plugin_id = found["plugin_id"]
        resolved_scope = found["scope"]
    elif "@" in plugin:
        plugin_id = plugin
        resolved_scope = "user"
    else:
        return PluginOperationResult(
            success=False,
            message=(
                f'Plugin "{plugin}" not found in any editable settings scope. '
                "Use plugin@marketplace format."
            ),
        )

    # Policy guard
    if enabled and _is_plugin_blocked_by_policy(plugin_id):
        return PluginOperationResult(
            success=False,
            message=f'Plugin "{plugin_id}" is blocked by your organization\'s policy and cannot be enabled',
        )

    setting_source = _scope_to_setting_source(resolved_scope)
    scope_settings = _get_settings_for_source(setting_source)
    scope_settings_value = (
        (scope_settings.get("enabledPlugins", {}) or {}).get(plugin_id)
        if scope_settings
        else None
    )

    # Cross-scope hint: explicit scope given but plugin is elsewhere
    is_override = (
        scope is not None
        and found is not None
        and SCOPE_PRECEDENCE.get(scope, 0) > SCOPE_PRECEDENCE.get(found.get("scope", "user"), 0)
    )

    if (
        scope is not None
        and scope_settings_value is None
        and found is not None
        and found.get("scope") != scope
        and not is_override
    ):
        return PluginOperationResult(
            success=False,
            message=(
                f'Plugin "{plugin}" is installed at {found["scope"]} scope, not {scope}. '
                f'Use --scope {found["scope"]} or omit --scope to auto-detect.'
            ),
        )

    # Check current state (for idempotency messaging)
    if scope is not None and not is_override:
        is_currently_enabled = scope_settings_value is True
    else:
        editable_scopes = _get_plugin_editable_scopes()
        is_currently_enabled = plugin_id in editable_scopes

    if enabled == is_currently_enabled:
        return PluginOperationResult(
            success=False,
            message=(
                f'Plugin "{plugin}" is already {"enabled" if enabled else "disabled"}'
                f'{f" at {scope} scope" if scope else ""}'
            ),
        )

    # Capture reverse dependents BEFORE disabling
    reverse_dependents: Optional[List[str]] = None
    if not enabled:
        loaded = await _load_all_plugins()
        all_plugins = loaded.get("enabled", []) + loaded.get("disabled", [])
        rdeps = _find_reverse_dependents(plugin_id, all_plugins)
        if rdeps:
            reverse_dependents = rdeps

    # ACTION: write settings
    current_scope_settings = _get_settings_for_source(setting_source)
    new_enabled_plugins = dict(
        (current_scope_settings.get("enabledPlugins", {}) or {}) if current_scope_settings else {}
    )
    new_enabled_plugins[plugin_id] = enabled

    result = _update_settings_for_source(setting_source, {"enabledPlugins": new_enabled_plugins})
    if result.get("error"):
        return PluginOperationResult(
            success=False,
            message=f"Failed to {operation} plugin: {result['error']}",
        )

    _clear_all_caches()

    parsed = _parse_plugin_identifier(plugin_id)
    dep_warn = _format_reverse_dependents_suffix(reverse_dependents or [])

    return PluginOperationResult(
        success=True,
        message=f"Successfully {operation}d plugin: {parsed['name']} (scope: {resolved_scope}){dep_warn}",
        plugin_id=plugin_id,
        plugin_name=parsed["name"],
        scope=resolved_scope,
        reverse_dependents=reverse_dependents,
    )


async def enable_plugin_op(
    plugin: str,
    scope: Optional[InstallableScope] = None,
) -> PluginOperationResult:
    """
    Enable a plugin.

    :param plugin: Plugin name or plugin@marketplace identifier
    :param scope: Optional scope. If not provided, auto-detects.
    :returns: Result indicating success/failure
    """
    return await set_plugin_enabled_op(plugin, True, scope)


async def disable_plugin_op(
    plugin: str,
    scope: Optional[InstallableScope] = None,
) -> PluginOperationResult:
    """
    Disable a plugin.

    :param plugin: Plugin name or plugin@marketplace identifier
    :param scope: Optional scope. If not provided, auto-detects.
    :returns: Result indicating success/failure
    """
    return await set_plugin_enabled_op(plugin, False, scope)


async def disable_all_plugins_op() -> PluginOperationResult:
    """
    Disable all enabled plugins.

    :returns: Result indicating success/failure with count of disabled plugins
    """
    enabled_plugins = _get_plugin_editable_scopes()

    if not enabled_plugins:
        return PluginOperationResult(success=True, message="No enabled plugins to disable")

    disabled: List[str] = []
    errors: List[str] = []

    for plugin_id in list(enabled_plugins.keys()):
        result = await set_plugin_enabled_op(plugin_id, False)
        if result.success:
            disabled.append(plugin_id)
        else:
            errors.append(f"{plugin_id}: {result.message}")

    plural = "plugin" if len(disabled) == 1 else "plugins"

    if errors:
        return PluginOperationResult(
            success=False,
            message=f"Disabled {len(disabled)} {plural}, {len(errors)} failed:\n" + "\n".join(errors),
        )

    return PluginOperationResult(
        success=True,
        message=f"Disabled {len(disabled)} {plural}",
    )


async def update_plugin_op(
    plugin: str,
    scope: PluginScope,
) -> PluginUpdateResult:
    """
    Update a plugin to the latest version.

    This function performs a NON-INPLACE update:
    1. Gets the plugin info from the marketplace
    2. For remote plugins: downloads to temp dir and calculates version
    3. For local plugins: calculates version from marketplace source
    4. If version differs from currently installed, copies to new versioned cache directory
    5. Updates installation in V2 file (memory stays unchanged until restart)
    6. Cleans up old version if no longer referenced by any installation

    :param plugin: Plugin name or plugin@marketplace identifier
    :param scope: Scope to update. Unlike install/uninstall/enable/disable, managed IS allowed.
    :returns: Result indicating success/failure with version info
    """
    from .installed_plugins_manager import (
        load_installed_plugins_from_disk,
        update_installation_path_on_disk,
    )

    parsed = _parse_plugin_identifier(plugin)
    plugin_name_str = parsed["name"] or plugin
    marketplace_name = parsed["marketplace"]
    plugin_id = f"{plugin_name_str}@{marketplace_name}" if marketplace_name else plugin

    # Get plugin info from marketplace
    try:
        from .marketplace_manager import get_plugin_by_id
        plugin_info = await get_plugin_by_id(plugin)
    except (ImportError, Exception) as e:
        return PluginUpdateResult(
            success=False,
            message=f'Plugin "{plugin_name_str}" not found: {e}',
            plugin_id=plugin_id,
            scope=scope,
        )

    if not plugin_info:
        return PluginUpdateResult(
            success=False,
            message=f'Plugin "{plugin_name_str}" not found',
            plugin_id=plugin_id,
            scope=scope,
        )

    entry = plugin_info.get("entry")
    marketplace_install_location = plugin_info.get("marketplace_install_location", "")

    # Get installations from disk
    disk_data = load_installed_plugins_from_disk()
    installations = disk_data.plugins.get(plugin_id)

    if not installations:
        return PluginUpdateResult(
            success=False,
            message=f'Plugin "{plugin_name_str}" is not installed',
            plugin_id=plugin_id,
            scope=scope,
        )

    project_path = get_project_path_for_scope(scope)
    installation = next(
        (i for i in installations if i.scope == scope and i.project_path == project_path),
        None,
    )

    if not installation:
        scope_desc = f"{scope} ({project_path})" if project_path else scope
        return PluginUpdateResult(
            success=False,
            message=f'Plugin "{plugin_name_str}" is not installed at scope {scope_desc}',
            plugin_id=plugin_id,
            scope=scope,
        )

    return await _perform_plugin_update(
        plugin_id=plugin_id,
        plugin_name=plugin_name_str,
        entry=entry,
        marketplace_install_location=marketplace_install_location,
        installation=installation,
        scope=scope,
        project_path=project_path,
    )


async def _perform_plugin_update(
    plugin_id: str,
    plugin_name: str,
    entry: Any,
    marketplace_install_location: str,
    installation: Any,
    scope: PluginScope,
    project_path: Optional[str],
) -> PluginUpdateResult:
    """
    Perform the actual plugin update: fetch source, calculate version, copy to cache.
    """
    import shutil

    from .installed_plugins_manager import (
        load_installed_plugins_from_disk,
        update_installation_path_on_disk,
    )

    old_version = getattr(installation, "version", None) or (
        installation.get("version") if isinstance(installation, dict) else None
    )
    old_install_path = getattr(installation, "install_path", None) or (
        installation.get("install_path") if isinstance(installation, dict) else None
    )

    try:
        from .plugin_loader import (
            cache_plugin,
            copy_plugin_to_versioned_cache,
            get_versioned_cache_path,
            get_versioned_zip_cache_path,
            load_plugin_manifest,
        )
        from .plugin_versioning import calculate_plugin_version
    except (ImportError, Exception) as e:
        return PluginUpdateResult(
            success=False,
            message=f"Failed to load plugin utilities: {e}",
            plugin_id=plugin_id,
            scope=scope,
        )

    source = getattr(entry, "source", None) or (entry.get("source") if isinstance(entry, dict) else None)
    entry_version = getattr(entry, "version", None) or (entry.get("version") if isinstance(entry, dict) else None)
    entry_name = getattr(entry, "name", None) or (entry.get("name") if isinstance(entry, dict) else plugin_name)

    source_path: Optional[str] = None
    new_version: str = "unknown"
    should_cleanup_source: bool = False
    git_commit_sha: Optional[str] = None

    try:
        if not isinstance(source, str):
            # Remote plugin: download to temp directory
            cache_result = await cache_plugin(source, {"manifest": {"name": entry_name}})
            source_path = cache_result.get("path", "")
            should_cleanup_source = True
            git_commit_sha = cache_result.get("git_commit_sha")

            new_version = await calculate_plugin_version(
                plugin_id,
                source,
                cache_result.get("manifest"),
                cache_result.get("path", ""),
                entry_version,
                cache_result.get("git_commit_sha"),
            )
        else:
            # Local plugin: use path from marketplace
            if not os.path.exists(marketplace_install_location):
                return PluginUpdateResult(
                    success=False,
                    message=f"Marketplace directory not found at {marketplace_install_location}",
                    plugin_id=plugin_id,
                    scope=scope,
                )

            marketplace_dir = (
                marketplace_install_location
                if os.path.isdir(marketplace_install_location)
                else os.path.dirname(marketplace_install_location)
            )
            source_path = os.path.join(marketplace_dir, source)

            if not os.path.exists(source_path):
                return PluginUpdateResult(
                    success=False,
                    message=f"Plugin source not found at {source_path}",
                    plugin_id=plugin_id,
                    scope=scope,
                )

            # Try to load manifest
            plugin_manifest = None
            manifest_path = os.path.join(source_path, ".claude-plugin", "plugin.json")
            try:
                plugin_manifest = await load_plugin_manifest(manifest_path, entry_name, source)
            except Exception:
                pass

            new_version = await calculate_plugin_version(
                plugin_id,
                source,
                plugin_manifest,
                source_path,
                entry_version,
            )

        # Check if this version already exists in cache
        versioned_path = get_versioned_cache_path(plugin_id, new_version)

        # Check if installation is already at the new version
        try:
            zip_path = get_versioned_zip_cache_path(plugin_id, new_version)
        except (AttributeError, Exception):
            zip_path = versioned_path + ".zip"

        is_up_to_date = (
            old_version == new_version
            or old_install_path == versioned_path
            or old_install_path == zip_path
        )

        if is_up_to_date:
            return PluginUpdateResult(
                success=True,
                message=f"{plugin_name} is already at the latest version ({new_version}).",
                plugin_id=plugin_id,
                new_version=new_version,
                old_version=old_version,
                already_up_to_date=True,
                scope=scope,
            )

        # Copy to versioned cache
        versioned_path = await copy_plugin_to_versioned_cache(
            source_path, plugin_id, new_version, entry
        )

        # Store old version path for potential cleanup
        old_version_path = old_install_path

        # Update disk JSON file for this installation
        update_installation_path_on_disk(
            plugin_id,
            scope,
            project_path,
            versioned_path,
            new_version,
            git_commit_sha,
        )

        if old_version_path and old_version_path != versioned_path:
            updated_disk_data = load_installed_plugins_from_disk()
            is_old_version_still_referenced = any(
                inst.install_path == old_version_path
                for plugin_installations in updated_disk_data.plugins.values()
                for inst in plugin_installations
            )
            if not is_old_version_still_referenced:
                _mark_plugin_version_orphaned(old_version_path)

        scope_desc = f"{scope} ({project_path})" if project_path else scope
        message = (
            f'Plugin "{plugin_name}" updated from {old_version or "unknown"} to {new_version} '
            f"for scope {scope_desc}. Restart to apply changes."
        )

        return PluginUpdateResult(
            success=True,
            message=message,
            plugin_id=plugin_id,
            new_version=new_version,
            old_version=old_version,
            scope=scope,
        )
    finally:
        # Clean up temp source if it was a remote download
        if should_cleanup_source and source_path:
            try:
                expected_cache = get_versioned_cache_path(plugin_id, new_version)
                if source_path != expected_cache:
                    shutil.rmtree(source_path, ignore_errors=True)
            except Exception:
                pass
