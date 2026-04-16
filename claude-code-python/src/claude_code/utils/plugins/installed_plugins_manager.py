"""
Manages plugin installation metadata stored in installed_plugins.json.

Ported from utils/plugins/installedPluginsManager.ts (1268 lines).

This module separates plugin installation state (global) from enabled/disabled
state (per-repository). The installed_plugins.json file tracks:
- Which plugins are installed globally
- Installation metadata (version, timestamps, paths)

The enabled/disabled state remains in .claude/settings.json for per-repo control.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import (
    InstalledPlugin,
    InstalledPluginsFileV1,
    InstalledPluginsFileV2,
    PluginInstallationEntry,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level caches (equivalent to TS module-level let variables)
# ---------------------------------------------------------------------------

# Memoized cache of installed plugins data (V2 format)
_installed_plugins_cache_v2: Optional[InstalledPluginsFileV2] = None

# Session-level snapshot at startup — NOT updated by background operations
_in_memory_installed_plugins: Optional[InstalledPluginsFileV2] = None

# Migration state to prevent running migration multiple times per session
_migration_completed: bool = False

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# All scopes are persistable (no session-only scopes in Python port)
PersistableScope = str  # 'managed' | 'user' | 'project' | 'local'


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _get_plugins_directory() -> str:
    """Return the path to the plugins directory."""
    try:
        from .plugin_loader import get_plugins_directory
        return get_plugins_directory()
    except ImportError:
        home = os.path.expanduser("~")
        return os.path.join(home, ".claude", "plugins")


def get_installed_plugins_file_path() -> str:
    """Get the path to the installed_plugins.json file."""
    return os.path.join(_get_plugins_directory(), "installed_plugins.json")


def get_installed_plugins_v2_file_path() -> str:
    """Get the path to the legacy installed_plugins_v2.json file (used only during migration)."""
    return os.path.join(_get_plugins_directory(), "installed_plugins_v2.json")


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def clear_installed_plugins_cache() -> None:
    """
    Clear the installed plugins cache.
    Call this when the file is modified to force a reload.

    Note: Also clears the in-memory session state.
    """
    global _installed_plugins_cache_v2, _in_memory_installed_plugins
    _installed_plugins_cache_v2 = None
    _in_memory_installed_plugins = None
    logger.debug("Cleared installed plugins cache")


def reset_migration_state() -> None:
    """Reset migration state (for testing)."""
    global _migration_completed
    _migration_completed = False


def reset_in_memory_state() -> None:
    """
    Reset the in-memory session state.
    Should only be called at startup or for testing.
    """
    global _in_memory_installed_plugins
    _in_memory_installed_plugins = None


# ---------------------------------------------------------------------------
# Raw file I/O
# ---------------------------------------------------------------------------

def _read_installed_plugins_file_raw() -> Optional[Dict[str, Any]]:
    """
    Read raw file data from installed_plugins.json.
    Returns None if file doesn't exist.
    Raises on parse errors.
    """
    file_path = get_installed_plugins_file_path()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        version = data.get("version", 1) if isinstance(data, dict) else 1
        return {"version": version, "data": data}
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(f"Failed to read installed_plugins.json: {e}") from e


def _write_installed_plugins_v2(data: InstalledPluginsFileV2) -> None:
    """Write V2 data to installed_plugins.json and update in-memory cache."""
    global _installed_plugins_cache_v2
    file_path = get_installed_plugins_file_path()
    plugins_dir = _get_plugins_directory()
    try:
        os.makedirs(plugins_dir, exist_ok=True)
        payload: Dict[str, Any] = {
            "version": data.version,
            "plugins": {
                plugin_id: [_entry_to_dict(e) for e in entries]
                for plugin_id, entries in data.plugins.items()
            },
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        _installed_plugins_cache_v2 = data
        logger.debug("Saved %d installed plugins to %s", len(data.plugins), file_path)
    except OSError as e:
        logger.error("Failed to save installed plugins: %s", e)
        raise


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _entry_to_dict(entry: PluginInstallationEntry) -> Dict[str, Any]:
    """Convert a PluginInstallationEntry dataclass to a JSON-serialisable dict."""
    d: Dict[str, Any] = {
        "scope": entry.scope,
        "installPath": entry.install_path,
    }
    if entry.project_path is not None:
        d["projectPath"] = entry.project_path
    if entry.version is not None:
        d["version"] = entry.version
    if entry.installed_at is not None:
        d["installedAt"] = entry.installed_at
    if entry.last_updated is not None:
        d["lastUpdated"] = entry.last_updated
    if entry.git_commit_sha is not None:
        d["gitCommitSha"] = entry.git_commit_sha
    return d


def _dict_to_entry(d: Dict[str, Any]) -> PluginInstallationEntry:
    """Convert a raw dict to a PluginInstallationEntry dataclass."""
    return PluginInstallationEntry(
        scope=d.get("scope", "user"),
        install_path=d.get("installPath", ""),
        project_path=d.get("projectPath"),
        version=d.get("version"),
        installed_at=d.get("installedAt"),
        last_updated=d.get("lastUpdated"),
        git_commit_sha=d.get("gitCommitSha"),
    )


def _parse_v2_data(raw_data: Dict[str, Any]) -> InstalledPluginsFileV2:
    """Parse a raw dict into InstalledPluginsFileV2."""
    plugins: Dict[str, List[PluginInstallationEntry]] = {}
    raw_plugins = raw_data.get("plugins", {})
    if isinstance(raw_plugins, dict):
        for plugin_id, entries in raw_plugins.items():
            if isinstance(entries, list):
                plugins[plugin_id] = [_dict_to_entry(e) for e in entries if isinstance(e, dict)]
    return InstalledPluginsFileV2(version=2, plugins=plugins)


def _parse_v1_data(raw_data: Dict[str, Any]) -> InstalledPluginsFileV1:
    """Parse a raw dict into InstalledPluginsFileV1."""
    plugins: Dict[str, InstalledPlugin] = {}
    raw_plugins = raw_data.get("plugins", {})
    if isinstance(raw_plugins, dict):
        for plugin_id, entry in raw_plugins.items():
            if isinstance(entry, dict):
                plugins[plugin_id] = InstalledPlugin(
                    version=entry.get("version", "unknown"),
                    installed_at=entry.get("installedAt", ""),
                    install_path=entry.get("installPath", ""),
                    last_updated=entry.get("lastUpdated"),
                    git_commit_sha=entry.get("gitCommitSha"),
                )
    return InstalledPluginsFileV1(version=1, plugins=plugins)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def _migrate_v1_to_v2(v1_data: InstalledPluginsFileV1) -> InstalledPluginsFileV2:
    """
    Migrate V1 data to V2 format.
    All V1 plugins are migrated to 'user' scope since V1 had no scope concept.
    """
    v2_plugins: Dict[str, List[PluginInstallationEntry]] = {}
    for plugin_id, plugin in v1_data.plugins.items():
        try:
            from .plugin_loader import get_versioned_cache_path
            versioned_cache_path = get_versioned_cache_path(plugin_id, plugin.version)
        except (ImportError, Exception):
            versioned_cache_path = plugin.install_path

        v2_plugins[plugin_id] = [
            PluginInstallationEntry(
                scope="user",
                install_path=versioned_cache_path,
                version=plugin.version,
                installed_at=plugin.installed_at,
                last_updated=plugin.last_updated,
                git_commit_sha=plugin.git_commit_sha,
            )
        ]
    return InstalledPluginsFileV2(version=2, plugins=v2_plugins)


def _cleanup_legacy_cache(v2_data: InstalledPluginsFileV2) -> None:
    """
    Clean up legacy non-versioned cache directories.

    Legacy cache structure: ~/.claude/plugins/cache/{plugin-name}/
    Versioned cache structure: ~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/
    """
    try:
        from .plugin_loader import get_plugin_cache_path
        cache_path = get_plugin_cache_path("")
        # get_plugin_cache_path includes marketplace — go up one level
        cache_base = os.path.dirname(cache_path)
    except (ImportError, Exception):
        return

    try:
        # Collect all install paths that are referenced
        referenced_paths = set(
            entry.install_path
            for entries in v2_data.plugins.values()
            for entry in entries
            if entry.install_path
        )

        if not os.path.isdir(cache_base):
            return

        for entry_name in os.listdir(cache_base):
            entry_path = os.path.join(cache_base, entry_name)
            if not os.path.isdir(entry_path):
                continue

            # Check if this is a versioned marketplace dir (has plugin/version subdirs)
            has_versioned_structure = False
            try:
                sub_entries = os.listdir(entry_path)
                for sub_name in sub_entries:
                    sub_path = os.path.join(entry_path, sub_name)
                    if os.path.isdir(sub_path):
                        version_entries = os.listdir(sub_path)
                        if any(os.path.isdir(os.path.join(sub_path, v)) for v in version_entries):
                            has_versioned_structure = True
                            break
            except OSError:
                continue

            if has_versioned_structure:
                continue  # Keep versioned marketplace dirs

            # Legacy flat cache directory
            if entry_path not in referenced_paths:
                try:
                    import shutil
                    shutil.rmtree(entry_path, ignore_errors=True)
                    logger.debug("Cleaned up legacy cache directory: %s", entry_name)
                except OSError:
                    pass
    except OSError as e:
        logger.warning("Failed to clean up legacy cache: %s", e)


def migrate_to_single_plugin_file() -> None:
    """
    Migrate to single plugin file format.

    This consolidates the V1/V2 dual-file system into a single file:
    1. If installed_plugins_v2.json exists: rename to installed_plugins.json (version=2)
    2. If only installed_plugins.json exists with version=1: convert to version=2 in-place
    3. Clean up legacy non-versioned cache directories

    This migration runs once per session at startup.
    """
    global _migration_completed
    if _migration_completed:
        return

    main_file_path = get_installed_plugins_file_path()
    v2_file_path = get_installed_plugins_v2_file_path()

    try:
        # Case 1: Try renaming v2→main; FileNotFoundError = v2 doesn't exist
        if os.path.exists(v2_file_path):
            try:
                os.rename(v2_file_path, main_file_path)
                logger.debug("Renamed installed_plugins_v2.json to installed_plugins.json")
                v2_data = load_installed_plugins_v2()
                _cleanup_legacy_cache(v2_data)
                _migration_completed = True
                return
            except OSError:
                pass

        # Case 2: v2 absent — try reading main
        if not os.path.exists(main_file_path):
            # Case 3: No file exists
            _migration_completed = True
            return

        try:
            with open(main_file_path, "r", encoding="utf-8") as f:
                main_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            _migration_completed = True
            return

        version = main_data.get("version", 1) if isinstance(main_data, dict) else 1

        if version == 1:
            v1_data = _parse_v1_data(main_data)
            v2_data = _migrate_v1_to_v2(v1_data)
            _write_installed_plugins_v2(v2_data)
            logger.debug(
                "Converted installed_plugins.json from V1 to V2 format (%d plugins)",
                len(v1_data.plugins),
            )
            _cleanup_legacy_cache(v2_data)
        # If version==2 already, no action needed

        _migration_completed = True
    except Exception as e:
        logger.error("Failed to migrate plugin files: %s", e)
        _migration_completed = True


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_installed_plugins_v2() -> InstalledPluginsFileV2:
    """
    Load installed plugins in V2 format.

    Reads from installed_plugins.json. If file has version=1, converts to V2
    in memory.

    Returns V2 format data with array-per-plugin structure.
    """
    global _installed_plugins_cache_v2

    if _installed_plugins_cache_v2 is not None:
        return _installed_plugins_cache_v2

    file_path = get_installed_plugins_file_path()

    try:
        raw = _read_installed_plugins_file_raw()

        if raw is not None:
            version = raw["version"]
            data = raw["data"]

            if version == 2:
                validated = _parse_v2_data(data)
                _installed_plugins_cache_v2 = validated
                logger.debug(
                    "Loaded %d installed plugins from %s",
                    len(validated.plugins),
                    file_path,
                )
                return validated

            # V1 format — convert
            v1_data = _parse_v1_data(data)
            v2_data = _migrate_v1_to_v2(v1_data)
            _installed_plugins_cache_v2 = v2_data
            logger.debug(
                "Loaded and converted %d plugins from V1 format",
                len(v1_data.plugins),
            )
            return v2_data

        # File doesn't exist
        logger.debug("installed_plugins.json doesn't exist, returning empty V2 object")
        _installed_plugins_cache_v2 = InstalledPluginsFileV2(version=2, plugins={})
        return _installed_plugins_cache_v2

    except Exception as e:
        logger.error("Failed to load installed_plugins.json: %s. Starting with empty state.", e)
        _installed_plugins_cache_v2 = InstalledPluginsFileV2(version=2, plugins={})
        return _installed_plugins_cache_v2


def load_installed_plugins_from_disk() -> InstalledPluginsFileV2:
    """
    Load installed plugins directly from disk, bypassing all caches.
    Used by background updater to check for changes without affecting the
    running session's view.
    """
    try:
        raw = _read_installed_plugins_file_raw()
        if raw is not None:
            if raw["version"] == 2:
                return _parse_v2_data(raw["data"])
            v1_data = _parse_v1_data(raw["data"])
            return _migrate_v1_to_v2(v1_data)
        return InstalledPluginsFileV2(version=2, plugins={})
    except Exception as e:
        logger.error("Failed to load installed plugins from disk: %s", e)
        return InstalledPluginsFileV2(version=2, plugins={})


# ---------------------------------------------------------------------------
# In-memory vs disk state
# ---------------------------------------------------------------------------

def get_in_memory_installed_plugins() -> InstalledPluginsFileV2:
    """
    Get the in-memory installed plugins (session state).
    This snapshot is loaded at startup and used for the entire session.
    It is NOT updated by background operations.
    """
    global _in_memory_installed_plugins
    if _in_memory_installed_plugins is None:
        _in_memory_installed_plugins = load_installed_plugins_v2()
    return _in_memory_installed_plugins


def update_installation_path_on_disk(
    plugin_id: str,
    scope: PersistableScope,
    project_path: Optional[str],
    new_path: str,
    new_version: str,
    git_commit_sha: Optional[str] = None,
) -> None:
    """
    Update a plugin's install path on disk only, without modifying in-memory state.
    Used by background updater to record new version on disk while session
    continues using the old version.
    """
    global _installed_plugins_cache_v2

    disk_data = load_installed_plugins_from_disk()
    installations = disk_data.plugins.get(plugin_id)

    if not installations:
        logger.debug("Cannot update %s on disk: plugin not found in installed plugins", plugin_id)
        return

    entry = next(
        (e for e in installations if e.scope == scope and e.project_path == project_path),
        None,
    )

    if entry is not None:
        entry.install_path = new_path
        entry.version = new_version
        entry.last_updated = datetime.now(timezone.utc).isoformat()
        if git_commit_sha is not None:
            entry.git_commit_sha = git_commit_sha

        file_path = get_installed_plugins_file_path()
        try:
            payload: Dict[str, Any] = {
                "version": disk_data.version,
                "plugins": {
                    pid: [_entry_to_dict(e) for e in entries]
                    for pid, entries in disk_data.plugins.items()
                },
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except OSError as e:
            logger.error("Failed to write installed plugins: %s", e)

        # Clear cache — disk changed — but do NOT update _in_memory_installed_plugins
        _installed_plugins_cache_v2 = None
        logger.debug("Updated %s on disk to version %s at %s", plugin_id, new_version, new_path)
    else:
        logger.debug(
            "Cannot update %s on disk: no installation for scope %s", plugin_id, scope
        )


# ---------------------------------------------------------------------------
# Pending updates helpers
# ---------------------------------------------------------------------------

def has_pending_updates() -> bool:
    """
    Check if there are pending updates (disk differs from memory).
    Returns True if any plugin has a different install path on disk vs memory.
    """
    memory_state = get_in_memory_installed_plugins()
    disk_state = load_installed_plugins_from_disk()

    for plugin_id, disk_installations in disk_state.plugins.items():
        memory_installations = memory_state.plugins.get(plugin_id)
        if not memory_installations:
            continue
        for disk_entry in disk_installations:
            memory_entry = next(
                (
                    m
                    for m in memory_installations
                    if m.scope == disk_entry.scope and m.project_path == disk_entry.project_path
                ),
                None,
            )
            if memory_entry and memory_entry.install_path != disk_entry.install_path:
                return True
    return False


def get_pending_update_count() -> int:
    """Get the count of pending updates (installations where disk differs from memory)."""
    count = 0
    memory_state = get_in_memory_installed_plugins()
    disk_state = load_installed_plugins_from_disk()

    for plugin_id, disk_installations in disk_state.plugins.items():
        memory_installations = memory_state.plugins.get(plugin_id)
        if not memory_installations:
            continue
        for disk_entry in disk_installations:
            memory_entry = next(
                (
                    m
                    for m in memory_installations
                    if m.scope == disk_entry.scope and m.project_path == disk_entry.project_path
                ),
                None,
            )
            if memory_entry and memory_entry.install_path != disk_entry.install_path:
                count += 1
    return count


def get_pending_updates_details() -> List[Dict[str, str]]:
    """
    Get details about pending updates for display.

    Returns a list of dicts with plugin_id, scope, old_version, new_version.
    """
    updates: List[Dict[str, str]] = []
    memory_state = get_in_memory_installed_plugins()
    disk_state = load_installed_plugins_from_disk()

    for plugin_id, disk_installations in disk_state.plugins.items():
        memory_installations = memory_state.plugins.get(plugin_id)
        if not memory_installations:
            continue
        for disk_entry in disk_installations:
            memory_entry = next(
                (
                    m
                    for m in memory_installations
                    if m.scope == disk_entry.scope and m.project_path == disk_entry.project_path
                ),
                None,
            )
            if memory_entry and memory_entry.install_path != disk_entry.install_path:
                updates.append(
                    {
                        "plugin_id": plugin_id,
                        "scope": disk_entry.scope,
                        "old_version": memory_entry.version or "unknown",
                        "new_version": disk_entry.version or "unknown",
                    }
                )
    return updates


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def add_plugin_installation(
    plugin_id: str,
    scope: PersistableScope,
    install_path: str,
    metadata: Optional[Dict[str, Any]] = None,
    project_path: Optional[str] = None,
) -> None:
    """
    Add or update a plugin installation entry at a specific scope.
    Used for V2 format where each plugin has an array of installations.
    """
    data = load_installed_plugins_from_disk()
    metadata = metadata or {}

    installations = list(data.plugins.get(plugin_id, []))

    existing_index = next(
        (
            i
            for i, e in enumerate(installations)
            if e.scope == scope and e.project_path == project_path
        ),
        None,
    )

    now = datetime.now(timezone.utc).isoformat()
    new_entry = PluginInstallationEntry(
        scope=scope,
        install_path=install_path,
        version=metadata.get("version"),
        installed_at=metadata.get("installed_at") or metadata.get("installedAt") or now,
        last_updated=now,
        git_commit_sha=metadata.get("git_commit_sha") or metadata.get("gitCommitSha"),
        project_path=project_path,
    )

    if existing_index is not None:
        installations[existing_index] = new_entry
        logger.debug("Updated installation for %s at scope %s", plugin_id, scope)
    else:
        installations.append(new_entry)
        logger.debug("Added installation for %s at scope %s", plugin_id, scope)

    data.plugins[plugin_id] = installations
    _write_installed_plugins_v2(data)


def remove_plugin_installation(
    plugin_id: str,
    scope: PersistableScope,
    project_path: Optional[str] = None,
) -> None:
    """
    Remove a plugin installation entry from a specific scope.
    """
    data = load_installed_plugins_from_disk()
    installations = data.plugins.get(plugin_id)

    if not installations:
        return

    data.plugins[plugin_id] = [
        e
        for e in installations
        if not (e.scope == scope and e.project_path == project_path)
    ]

    # Remove plugin entirely if no installations left
    if not data.plugins[plugin_id]:
        del data.plugins[plugin_id]

    _write_installed_plugins_v2(data)
    logger.debug("Removed installation for %s at scope %s", plugin_id, scope)


def add_installed_plugin(
    plugin_id: str,
    metadata: InstalledPlugin,
    scope: PersistableScope = "user",
    project_path: Optional[str] = None,
) -> None:
    """
    Add or update a plugin's installation metadata.

    Implements double-write: updates both V1 and V2 files.
    """
    v2_data = load_installed_plugins_from_disk()
    v2_entry = PluginInstallationEntry(
        scope=scope,
        install_path=metadata.install_path,
        version=metadata.version,
        installed_at=metadata.installed_at,
        last_updated=metadata.last_updated,
        git_commit_sha=metadata.git_commit_sha,
        project_path=project_path if project_path else None,
    )

    installations = list(v2_data.plugins.get(plugin_id, []))

    existing_index = next(
        (
            i
            for i, e in enumerate(installations)
            if e.scope == scope and e.project_path == project_path
        ),
        None,
    )

    is_update = existing_index is not None
    if is_update:
        installations[existing_index] = v2_entry
    else:
        installations.append(v2_entry)

    v2_data.plugins[plugin_id] = installations
    _write_installed_plugins_v2(v2_data)

    logger.debug(
        "%s installed plugin: %s (scope: %s)",
        "Updated" if is_update else "Added",
        plugin_id,
        scope,
    )


def remove_installed_plugin(plugin_id: str) -> Optional[InstalledPlugin]:
    """
    Remove a plugin from the installed plugins registry.
    Returns the removed plugin metadata, or None if it wasn't installed.

    Note: Only updates the registry file. Call delete_plugin_cache() afterward
    to remove the physical files.
    """
    v2_data = load_installed_plugins_from_disk()
    installations = v2_data.plugins.get(plugin_id)

    if not installations:
        return None

    # Extract V1-compatible metadata from first installation for return value
    first_install = installations[0] if installations else None
    metadata: Optional[InstalledPlugin] = None
    if first_install:
        metadata = InstalledPlugin(
            version=first_install.version or "unknown",
            installed_at=first_install.installed_at or datetime.now(timezone.utc).isoformat(),
            install_path=first_install.install_path,
            last_updated=first_install.last_updated,
            git_commit_sha=first_install.git_commit_sha,
        )

    del v2_data.plugins[plugin_id]
    _write_installed_plugins_v2(v2_data)

    logger.debug("Removed installed plugin: %s", plugin_id)
    return metadata


def delete_plugin_cache(install_path: str) -> None:
    """
    Delete a plugin's cache directory (physically removes plugin files from disk).
    """
    import shutil

    try:
        shutil.rmtree(install_path, ignore_errors=False)
        logger.debug("Deleted plugin cache at %s", install_path)

        # Clean up empty parent plugin directory (cache/{marketplace}/{plugin})
        try:
            from .plugin_loader import get_plugin_cache_path
            cache_base = os.path.dirname(get_plugin_cache_path(""))
        except (ImportError, Exception):
            cache_base = ""

        if cache_base and "/cache/" in install_path and install_path.startswith(cache_base):
            plugin_dir = os.path.dirname(install_path)
            if plugin_dir != cache_base and plugin_dir.startswith(cache_base):
                try:
                    if os.path.isdir(plugin_dir) and not os.listdir(plugin_dir):
                        os.rmdir(plugin_dir)
                        logger.debug("Deleted empty plugin directory at %s", plugin_dir)
                except OSError:
                    pass
    except OSError as e:
        raise RuntimeError(f"Failed to delete plugin cache at {install_path}: {e}") from e


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def is_installation_relevant_to_current_project(
    inst: PluginInstallationEntry,
) -> bool:
    """
    Predicate: is this installation relevant to the current project context?

    - user/managed scopes: always relevant (global)
    - project/local scopes: only if projectPath matches the current project
    """
    if inst.scope in ("user", "managed"):
        return True
    try:
        from ...bootstrap.state import get_original_cwd
        return inst.project_path == get_original_cwd()
    except (ImportError, Exception):
        return inst.scope in ("user", "managed")


def is_plugin_installed(plugin_id: str) -> bool:
    """
    Check if a plugin is installed in a way relevant to the current project.

    Returns True if the plugin has a user/managed-scoped installation, OR a
    project/local-scoped installation whose project_path matches the current project.
    """
    v2_data = load_installed_plugins_v2()
    installations = v2_data.plugins.get(plugin_id)
    if not installations:
        return False
    if not any(is_installation_relevant_to_current_project(i) for i in installations):
        return False

    # Check settings divergence guard
    try:
        from ..settings.settings import get_settings_deprecated
        settings = get_settings_deprecated()
        enabled_plugins = settings.get("enabledPlugins", {}) if settings else {}
        return plugin_id in enabled_plugins
    except (ImportError, Exception):
        return True


def is_plugin_globally_installed(plugin_id: str) -> bool:
    """
    True only if the plugin has a USER or MANAGED scope installation.

    Use this in UI flows that decide whether to offer installation at all.
    """
    v2_data = load_installed_plugins_v2()
    installations = v2_data.plugins.get(plugin_id)
    if not installations:
        return False
    has_global_entry = any(e.scope in ("user", "managed") for e in installations)
    if not has_global_entry:
        return False
    try:
        from ..settings.settings import get_settings_deprecated
        settings = get_settings_deprecated()
        enabled_plugins = settings.get("enabledPlugins", {}) if settings else {}
        return plugin_id in enabled_plugins
    except (ImportError, Exception):
        return True


def remove_all_plugins_for_marketplace(
    marketplace_name: str,
) -> Dict[str, Any]:
    """
    Remove all plugin entries belonging to a specific marketplace from
    installed_plugins.json.

    Returns dict with orphaned_paths and removed_plugin_ids.
    """
    if not marketplace_name:
        return {"orphaned_paths": [], "removed_plugin_ids": []}

    data = load_installed_plugins_from_disk()
    suffix = f"@{marketplace_name}"
    orphaned_paths: set = set()
    removed_plugin_ids: List[str] = []

    for plugin_id in list(data.plugins.keys()):
        if not plugin_id.endswith(suffix):
            continue

        for entry in data.plugins.get(plugin_id, []):
            if entry.install_path:
                orphaned_paths.add(entry.install_path)

        del data.plugins[plugin_id]
        removed_plugin_ids.append(plugin_id)
        logger.debug("Removed installed plugin for marketplace removal: %s", plugin_id)

    if removed_plugin_ids:
        _write_installed_plugins_v2(data)

    return {
        "orphaned_paths": list(orphaned_paths),
        "removed_plugin_ids": removed_plugin_ids,
    }


# ---------------------------------------------------------------------------
# Plugin version helper
# ---------------------------------------------------------------------------

def _get_plugin_version_from_manifest(plugin_cache_path: str, plugin_id: str) -> str:
    """Try to read version from plugin manifest."""
    manifest_path = os.path.join(plugin_cache_path, ".claude-plugin", "plugin.json")
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        return manifest.get("version") or "unknown"
    except (OSError, json.JSONDecodeError):
        logger.debug("Could not read version from manifest for %s", plugin_id)
        return "unknown"


async def _get_git_commit_sha(dir_path: str) -> Optional[str]:
    """Get the git commit SHA from a git repository directory."""
    try:
        from ..git.git_filesystem import get_head_for_dir
        sha = await get_head_for_dir(dir_path)
        return sha or None
    except (ImportError, Exception):
        return None


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

async def initialize_versioned_plugins() -> None:
    """
    Initialize the versioned plugins system.

    This triggers V1→V2 migration and initializes the in-memory session state.
    Should be called early during startup.
    """
    # Step 1: Migrate to single file format
    migrate_to_single_plugin_file()

    # Step 2: Sync enabledPlugins from settings.json to installed_plugins.json
    try:
        await migrate_from_enabled_plugins()
    except Exception as e:
        logger.error("migrate_from_enabled_plugins failed: %s", e)

    # Step 3: Initialize in-memory session state
    data = get_in_memory_installed_plugins()
    logger.debug(
        "Initialized versioned plugins system with %d plugins",
        len(data.plugins),
    )


async def migrate_from_enabled_plugins() -> None:
    """
    Sync installed_plugins.json with enabledPlugins from settings.

    For each plugin in enabledPlugins that's not in installed_plugins.json:
    - Queries marketplace to get actual install path
    - Extracts version from manifest if available
    - Captures git commit SHA for git-based plugins
    """
    try:
        from ..settings.settings import get_settings_deprecated, get_settings_for_source
    except (ImportError, Exception):
        return

    try:
        settings = get_settings_deprecated()
        enabled_plugins: Dict[str, Any] = {}
        if settings and isinstance(settings, dict):
            enabled_plugins = settings.get("enabledPlugins", {})
    except (ImportError, Exception):
        return

    if not enabled_plugins:
        return

    # Check if main file exists and is already V2
    raw_file_data = _read_installed_plugins_file_raw()
    file_exists = raw_file_data is not None
    is_v2_format = file_exists and raw_file_data is not None and raw_file_data["version"] == 2

    if is_v2_format and raw_file_data is not None:
        existing_data = _parse_v2_data(raw_file_data["data"])
        all_plugins_exist = all(
            plugin_id in existing_data.plugins and existing_data.plugins[plugin_id]
            for plugin_id in enabled_plugins
            if "@" in plugin_id
        )
        if all_plugins_exist:
            logger.debug("All plugins already exist, skipping migration")
            return

    logger.debug(
        "%s installed_plugins.json with enabledPlugins from settings.json files",
        "Syncing" if file_exists else "Creating",
    )

    now = datetime.now(timezone.utc).isoformat()

    try:
        from ...utils.cwd import get_cwd
        project_path = get_cwd()
    except (ImportError, Exception):
        project_path = os.getcwd()

    # Step 1: Build map of pluginId → scope from all settings.json files
    plugin_scope_from_settings: Dict[str, Dict[str, Any]] = {}

    setting_sources = ["userSettings", "projectSettings", "localSettings"]
    scope_map = {"userSettings": "user", "projectSettings": "project", "localSettings": "local"}

    for source in setting_sources:
        try:
            source_settings = get_settings_for_source(source)
            source_enabled = source_settings.get("enabledPlugins", {}) if source_settings else {}
        except (ImportError, Exception):
            source_enabled = {}

        for plugin_id in source_enabled:
            if "@" not in plugin_id:
                continue
            scope = scope_map.get(source, "user")
            plugin_scope_from_settings[plugin_id] = {
                "scope": scope,
                "project_path": None if scope == "user" else project_path,
            }

    # Step 2: Start with existing data
    if file_exists:
        existing_v2 = load_installed_plugins_v2()
        v2_plugins = dict(existing_v2.plugins)
    else:
        v2_plugins = {}

    # Step 3: Update/add entries
    updated_count = 0
    added_count = 0

    for plugin_id, scope_info in plugin_scope_from_settings.items():
        existing_installations = v2_plugins.get(plugin_id)
        scope = scope_info["scope"]
        p_path = scope_info["project_path"]

        if existing_installations:
            existing_entry = existing_installations[0]
            if existing_entry.scope != scope or existing_entry.project_path != p_path:
                existing_entry.scope = scope
                if p_path:
                    existing_entry.project_path = p_path
                else:
                    existing_entry.project_path = None
                existing_entry.last_updated = now
                updated_count += 1
                logger.debug("Updated %s scope to %s (settings is source of truth)", plugin_id, scope)
        else:
            # Plugin not in V2 — try to add via marketplace lookup
            try:
                from .marketplace_manager import get_plugin_by_id
                from .plugin_loader import get_plugin_cache_path, get_versioned_cache_path

                plugin_info = await get_plugin_by_id(plugin_id)
                if not plugin_info:
                    logger.debug("Plugin %s not found in any marketplace, skipping", plugin_id)
                    continue

                entry = plugin_info["entry"]
                marketplace_install_location = plugin_info["marketplace_install_location"]

                if isinstance(entry.get("source"), str):
                    install_path_candidate = os.path.join(
                        marketplace_install_location, entry["source"]
                    )
                    version = _get_plugin_version_from_manifest(install_path_candidate, plugin_id)
                    git_commit_sha = await _get_git_commit_sha(install_path_candidate)
                else:
                    plugin_name = plugin_id.split("@")[0] if "@" in plugin_id else plugin_id
                    sanitized_name = "".join(
                        c if c.isalnum() or c in "-_" else "-" for c in plugin_name
                    )
                    plugin_cache_path_candidate = get_plugin_cache_path(plugin_id)
                    if not os.path.isdir(plugin_cache_path_candidate):
                        logger.debug("External plugin %s not in cache, skipping", plugin_id)
                        continue
                    install_path_candidate = plugin_cache_path_candidate
                    dir_entries = os.listdir(plugin_cache_path_candidate)
                    version = "unknown"
                    if ".claude-plugin" in dir_entries:
                        version = _get_plugin_version_from_manifest(
                            plugin_cache_path_candidate, plugin_id
                        )
                    git_commit_sha = await _get_git_commit_sha(plugin_cache_path_candidate)

                if version == "unknown" and entry.get("version"):
                    version = entry["version"]
                if version == "unknown" and git_commit_sha:
                    version = git_commit_sha[:12]

                versioned_path = get_versioned_cache_path(plugin_id, version)
                new_entry = PluginInstallationEntry(
                    scope=scope,
                    install_path=versioned_path,
                    version=version,
                    installed_at=now,
                    last_updated=now,
                    git_commit_sha=git_commit_sha,
                    project_path=p_path,
                )
                v2_plugins[plugin_id] = [new_entry]
                added_count += 1
                logger.debug("Added %s with scope %s", plugin_id, scope)
            except Exception as e:
                logger.debug("Failed to add plugin %s: %s", plugin_id, e)

    # Step 4: Save
    if not file_exists or updated_count > 0 or added_count > 0:
        v2_data = InstalledPluginsFileV2(version=2, plugins=v2_plugins)
        _write_installed_plugins_v2(v2_data)
        logger.debug(
            "Sync completed: %d added, %d updated in installed_plugins.json",
            added_count,
            updated_count,
        )
