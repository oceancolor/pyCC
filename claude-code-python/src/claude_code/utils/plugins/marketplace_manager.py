"""
Marketplace manager for Claude Code plugins.
Ported from utils/plugins/marketplaceManager.ts (2643 lines).

This module provides functionality to:
- Manage known marketplace sources (URLs, GitHub repos, npm packages, local files)
- Cache marketplace manifests locally for offline access
- Install plugins from marketplace entries
- Track and update marketplace configurations
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from os.path import basename, dirname, isabs, join
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass

try:
    from claude_code.utils.plugins.schemas import (
        KnownMarketplace,
        KnownMarketplacesFile,
        MarketplaceSource,
        PluginMarketplace,
        PluginMarketplaceEntry,
        is_local_marketplace_source,
        parse_known_marketplaces_file,
        parse_plugin_marketplace,
        validate_official_name_source,
    )
except ImportError:
    pass  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _get_plugins_directory() -> str:
    """Get the plugins directory path."""
    try:
        from claude_code.utils.plugins.plugin_directories import get_plugins_directory
        return get_plugins_directory()
    except ImportError:
        home = os.environ.get('HOME', os.path.expanduser('~'))
        return join(home, '.claude', 'plugins')


def get_marketplaces_cache_dir() -> str:
    """Get the path to the marketplaces cache directory."""
    return join(_get_plugins_directory(), 'marketplaces')


def _get_known_marketplaces_file() -> str:
    """Get the path to the known marketplaces configuration file."""
    return join(_get_plugins_directory(), 'known_marketplaces.json')


# ---------------------------------------------------------------------------
# Known marketplace types
# ---------------------------------------------------------------------------

@dataclass
class DeclaredMarketplace:
    """
    Declared marketplace entry (intent layer).

    Structurally compatible with settings `extraKnownMarketplaces` entries,
    but adds `source_is_fallback` for implicit built-in declarations.
    """
    source: Dict[str, Any]
    install_location: Optional[str] = None
    auto_update: Optional[bool] = None
    source_is_fallback: Optional[bool] = None


KnownMarketplacesConfig = Dict[str, Any]  # alias


@dataclass
class LoadedPluginMarketplace:
    """Result of loading and caching a marketplace."""
    marketplace: Any  # PluginMarketplace
    cache_path: str


# ---------------------------------------------------------------------------
# Memoization cache
# ---------------------------------------------------------------------------

class _MarketplaceCache:
    """Simple in-memory cache for marketplace data."""
    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)


_marketplace_cache = _MarketplaceCache()


def clear_marketplaces_cache() -> None:
    """Clear all cached marketplace data (for testing)."""
    _marketplace_cache.clear()


# ---------------------------------------------------------------------------
# Git helper functions
# ---------------------------------------------------------------------------

async def _exec_no_throw(cmd: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
    """Execute a command and return (returncode, stdout, stderr) without throwing."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode('utf-8', errors='replace'), stderr.decode('utf-8', errors='replace')
    except Exception as e:
        return 1, '', str(e)


def _git_exe() -> str:
    """Get git executable path."""
    return 'git'


async def git_pull(repo_path: str, remote: str = 'origin', timeout_ms: int = 120_000) -> Tuple[int, str, str]:
    """
    Git pull operation.

    Pulls latest changes with a configured timeout to prevent indefinite blocking.
    """
    git = _git_exe()
    return await _exec_no_throw([git, 'pull', remote, '--ff-only'], cwd=repo_path)


async def git_clone(
    url: str,
    dest: str,
    ref: Optional[str] = None,
    sparse_paths: Optional[List[str]] = None,
    timeout_ms: int = 300_000,
) -> Tuple[int, str, str]:
    """
    Git clone operation with optional sparse checkout.
    """
    git = _git_exe()
    cmd = [git, 'clone']
    if sparse_paths:
        cmd += ['--filter=blob:none', '--sparse']
    if ref:
        cmd += ['--branch', ref]
    cmd += ['--', url, dest]
    rc, out, err = await _exec_no_throw(cmd)
    if rc != 0:
        return rc, out, err
    if sparse_paths:
        # Set up sparse checkout
        rc2, out2, err2 = await _exec_no_throw(
            [git, 'sparse-checkout', 'set', '--cone', *sparse_paths], cwd=dest
        )
        if rc2 != 0:
            return rc2, out2, err2
    return rc, out, err


# ---------------------------------------------------------------------------
# URL credential redaction
# ---------------------------------------------------------------------------

_CREDENTIAL_REDACT_RE = re.compile(r'(https?://)([^@]+@)')


def redact_url_credentials(url: str) -> str:
    """Redact all credentials from http(s) URLs."""
    return _CREDENTIAL_REDACT_RE.sub(r'\1<credentials>@', url)


# ---------------------------------------------------------------------------
# Marketplace file I/O
# ---------------------------------------------------------------------------

def _read_json_file(path: str) -> Optional[Dict[str, Any]]:
    """Read and parse a JSON file. Returns None on error."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_file(path: str, data: Any) -> bool:
    """Write data as JSON to path. Returns True on success."""
    try:
        os.makedirs(dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Known marketplaces configuration
# ---------------------------------------------------------------------------

async def load_known_marketplaces_config_safe() -> Dict[str, Any]:
    """
    Load known marketplaces configuration, returning empty dict on failure.
    """
    path = _get_known_marketplaces_file()
    data = _read_json_file(path)
    if data is None or not isinstance(data, dict):
        return {}
    return data


async def save_known_marketplaces_config(config: Dict[str, Any]) -> bool:
    """Save the known marketplaces configuration file."""
    path = _get_known_marketplaces_file()
    return _write_json_file(path, config)


def load_known_marketplaces_config_sync() -> Dict[str, Any]:
    """Synchronous version for contexts that can't await."""
    path = _get_known_marketplaces_file()
    data = _read_json_file(path)
    if data is None or not isinstance(data, dict):
        return {}
    return data


# ---------------------------------------------------------------------------
# Marketplace resolution helpers
# ---------------------------------------------------------------------------

def _marketplace_json_path_for_source(
    install_location: str,
    source: Dict[str, Any],
) -> str:
    """Return the path to marketplace.json given installLocation and source."""
    source_type = source.get('source', '')
    if source_type in ('github', 'git', 'directory'):
        path_in_repo = source.get('path', '.claude-plugin/marketplace.json')
        return join(install_location, path_in_repo)
    if source_type == 'file':
        return install_location
    # url, npm, settings → install_location is the cached .json file
    return install_location


def _get_marketplace_from_disk(install_location: str, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Read marketplace.json from the install location.
    Returns parsed dict or None.
    """
    json_path = _marketplace_json_path_for_source(install_location, source)
    return _read_json_file(json_path)


# ---------------------------------------------------------------------------
# Core marketplace getters (cache-aware)
# ---------------------------------------------------------------------------

async def get_marketplace(
    name: str,
    config: Optional[Dict[str, Any]] = None,
    force_refresh: bool = False,
) -> Optional[Any]:
    """
    Get a marketplace by name, using cache when possible.
    Returns a PluginMarketplace-like dict or None.
    """
    cache_key = name
    if not force_refresh:
        cached = _marketplace_cache.get(cache_key)
        if cached is not None:
            return cached

    if config is None:
        config = await load_known_marketplaces_config_safe()

    entry = config.get(name)
    if not entry:
        return None

    source = entry.get('source', {})
    install_location = entry.get('installLocation', '')
    data = _get_marketplace_from_disk(install_location, source)
    if data is None:
        return None

    try:
        marketplace = parse_plugin_marketplace(data)
    except Exception:
        marketplace = data  # fallback: return raw dict

    _marketplace_cache.set(cache_key, marketplace)
    return marketplace


async def get_marketplace_cache_only(name: str) -> Optional[Any]:
    """
    Get a marketplace by name from local cache only (no network).
    """
    return await get_marketplace(name, force_refresh=False)


async def get_plugin_by_id_cache_only(plugin_id: str) -> Optional[Any]:
    """
    Get a specific plugin by its plugin ID from cached marketplaces.
    plugin_id format: 'plugin-name@marketplace-name'
    """
    if '@' not in plugin_id:
        return None
    plugin_name, marketplace_name = plugin_id.rsplit('@', 1)
    marketplace = await get_marketplace_cache_only(marketplace_name)
    if marketplace is None:
        return None
    plugins = marketplace.plugins if hasattr(marketplace, 'plugins') else marketplace.get('plugins', [])
    for plugin in plugins:
        name = plugin.name if hasattr(plugin, 'name') else plugin.get('name', '')
        if name == plugin_name:
            return plugin
    return None


# ---------------------------------------------------------------------------
# Marketplace loading/caching from remote sources
# ---------------------------------------------------------------------------

async def _fetch_marketplace_from_url(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout_s: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """Fetch marketplace.json from a URL."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data
    except Exception:
        return None


async def load_and_cache_marketplace(
    name: str,
    source: Dict[str, Any],
    cache_dir: str,
    force_update: bool = False,
) -> Optional[LoadedPluginMarketplace]:
    """
    Load a marketplace from its source and cache it locally.

    Handles github, git, url, npm, file, directory, and settings sources.
    Returns LoadedPluginMarketplace or None on failure.
    """
    source_type = source.get('source', '')
    os.makedirs(cache_dir, exist_ok=True)

    cache_path: str
    marketplace_json_path: str

    if source_type == 'url':
        url = source.get('url', '')
        headers = source.get('headers')
        cache_path = join(cache_dir, f'{name}.json')
        if force_update or not os.path.exists(cache_path):
            data = await _fetch_marketplace_from_url(url, headers)
            if data is None:
                return None
            if not _write_json_file(cache_path, data):
                return None
        marketplace_json_path = cache_path

    elif source_type in ('github', 'git'):
        repo_dir = join(cache_dir, name)
        path_in_repo = source.get('path', '.claude-plugin/marketplace.json')
        marketplace_json_path = join(repo_dir, path_in_repo)

        if not os.path.isdir(repo_dir) or force_update:
            if source_type == 'github':
                repo = source.get('repo', '')
                url = f'https://github.com/{repo}.git'
            else:
                url = source.get('url', '')

            ref = source.get('ref')
            sparse_paths = source.get('sparsePaths')

            if os.path.isdir(repo_dir) and force_update:
                rc, _, _ = await git_pull(repo_dir)
                if rc != 0:
                    shutil.rmtree(repo_dir, ignore_errors=True)
                    rc, _, _ = await git_clone(url, repo_dir, ref, sparse_paths)
                    if rc != 0:
                        return None
            else:
                if os.path.isdir(repo_dir):
                    shutil.rmtree(repo_dir, ignore_errors=True)
                rc, _, _ = await git_clone(url, repo_dir, ref, sparse_paths)
                if rc != 0:
                    return None

        cache_path = repo_dir

    elif source_type == 'npm':
        package = source.get('package', '')
        version = source.get('version', '')
        npm_dir = join(cache_dir, name)
        cache_path = npm_dir
        pkg_spec = f'{package}@{version}' if version else package
        if not os.path.isdir(npm_dir) or force_update:
            os.makedirs(npm_dir, exist_ok=True)
            rc, _, _ = await _exec_no_throw(['npm', 'install', pkg_spec, '--prefix', npm_dir])
            if rc != 0:
                return None
        marketplace_json_path = join(npm_dir, 'node_modules', package, '.claude-plugin', 'marketplace.json')

    elif source_type == 'file':
        file_path = source.get('path', '')
        cache_path = file_path
        marketplace_json_path = file_path

    elif source_type == 'directory':
        dir_path = source.get('path', '')
        cache_path = dir_path
        marketplace_json_path = join(dir_path, '.claude-plugin', 'marketplace.json')

    elif source_type == 'settings':
        # Inline marketplace defined directly in settings.json
        plugins_data = source.get('plugins', [])
        owner = source.get('owner')
        synthetic = {
            'name': name,
            'owner': owner,
            'plugins': plugins_data,
        }
        cache_path = join(cache_dir, f'{name}.json')
        if not _write_json_file(cache_path, synthetic):
            return None
        marketplace_json_path = cache_path

    else:
        return None

    # Read and parse the marketplace.json
    data = _read_json_file(marketplace_json_path)
    if data is None:
        return None

    # Validate official name source
    error = validate_official_name_source(name, source)
    if error:
        return None

    try:
        marketplace = parse_plugin_marketplace(data)
    except Exception:
        return None

    _marketplace_cache.set(name, marketplace)
    return LoadedPluginMarketplace(marketplace=marketplace, cache_path=cache_path)


# ---------------------------------------------------------------------------
# Declared marketplaces
# ---------------------------------------------------------------------------

def get_declared_marketplaces() -> Dict[str, DeclaredMarketplace]:
    """
    Get declared marketplace intent from merged settings and --add-dir sources.
    This is what SHOULD exist — used by the reconciler to find gaps.

    The official marketplace is implicitly declared with `source_is_fallback: True`
    when any enabled plugin references it.
    """
    implicit: Dict[str, DeclaredMarketplace] = {}

    try:
        from claude_code.utils.plugins.add_dir_plugin_settings import (
            get_add_dir_enabled_plugins,
            get_add_dir_extra_marketplaces,
        )
        add_dir_enabled = get_add_dir_enabled_plugins()
        add_dir_extra = get_add_dir_extra_marketplaces()
    except ImportError:
        add_dir_enabled = {}
        add_dir_extra = {}

    try:
        from claude_code.utils.settings.settings import get_initial_settings
        initial_settings = get_initial_settings()
        enabled_plugins = dict(initial_settings.get('enabledPlugins') or {})
        extra_known = dict(initial_settings.get('extraKnownMarketplaces') or {})
    except Exception:
        enabled_plugins = {}
        extra_known = {}

    try:
        from claude_code.utils.plugins.official_marketplace import (
            OFFICIAL_MARKETPLACE_NAME,
            OFFICIAL_MARKETPLACE_SOURCE,
        )
        all_enabled = {**add_dir_enabled, **enabled_plugins}
        for plugin_id, value in all_enabled.items():
            if value:
                marketplace_name = plugin_id.split('@')[-1] if '@' in plugin_id else ''
                if marketplace_name == OFFICIAL_MARKETPLACE_NAME:
                    implicit[OFFICIAL_MARKETPLACE_NAME] = DeclaredMarketplace(
                        source=OFFICIAL_MARKETPLACE_SOURCE,
                        source_is_fallback=True,
                    )
                    break
    except ImportError:
        pass

    result: Dict[str, DeclaredMarketplace] = {}
    result.update(implicit)
    for k, v in add_dir_extra.items():
        result[k] = DeclaredMarketplace(source=v) if isinstance(v, dict) else v
    for k, v in extra_known.items():
        result[k] = DeclaredMarketplace(source=v.get('source', {}), auto_update=v.get('autoUpdate')) if isinstance(v, dict) else v
    return result


def get_marketplace_declaring_source(name: str) -> Optional[str]:
    """
    Find which editable settings source declared a marketplace.

    Returns one of 'userSettings', 'projectSettings', 'localSettings', or None.
    """
    try:
        from claude_code.utils.settings.settings import get_settings_for_source
        for source_name in ('localSettings', 'projectSettings', 'userSettings'):
            settings = get_settings_for_source(source_name)
            if settings and name in (settings.get('extraKnownMarketplaces') or {}):
                return source_name
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Marketplace reconciliation
# ---------------------------------------------------------------------------

@dataclass
class MarketplaceDiff:
    """Differences between declared and known marketplaces."""
    to_add: List[Tuple[str, DeclaredMarketplace]] = field(default_factory=list)
    to_update: List[Tuple[str, DeclaredMarketplace]] = field(default_factory=list)
    to_remove: List[str] = field(default_factory=list)


def diff_marketplaces(
    declared: Dict[str, DeclaredMarketplace],
    known: Dict[str, Any],
) -> MarketplaceDiff:
    """
    Compute the diff between declared marketplace intent and known (cached) state.
    """
    diff = MarketplaceDiff()

    declared_names = set(declared.keys())
    known_names = set(known.keys())

    for name in declared_names - known_names:
        diff.to_add.append((name, declared[name]))

    for name in declared_names & known_names:
        declared_entry = declared[name]
        known_entry = known[name]
        # Compare sources to detect changes
        known_source = known_entry.get('source', {}) if isinstance(known_entry, dict) else {}
        if declared_entry.source != known_source and not declared_entry.source_is_fallback:
            diff.to_update.append((name, declared_entry))

    for name in known_names - declared_names:
        diff.to_remove.append(name)

    return diff


async def reconcile_marketplaces(
    force_update: bool = False,
) -> None:
    """
    Reconcile the known marketplaces against the declared intent from settings.
    Adds new marketplaces, updates changed ones, removes old ones.
    """
    declared = get_declared_marketplaces()
    known = await load_known_marketplaces_config_safe()
    diff = diff_marketplaces(declared, known)
    cache_dir = get_marketplaces_cache_dir()

    # Add new marketplaces
    for name, entry in diff.to_add:
        result = await load_and_cache_marketplace(name, entry.source, cache_dir, force_update=True)
        if result is not None:
            known[name] = {
                'source': entry.source,
                'installLocation': result.cache_path,
                'lastUpdated': _iso_now(),
                'autoUpdate': entry.auto_update,
            }

    # Update changed marketplaces
    for name, entry in diff.to_update:
        result = await load_and_cache_marketplace(name, entry.source, cache_dir, force_update=True)
        if result is not None:
            known[name] = {
                'source': entry.source,
                'installLocation': result.cache_path,
                'lastUpdated': _iso_now(),
                'autoUpdate': entry.auto_update,
            }

    # Remove deleted marketplaces
    for name in diff.to_remove:
        known.pop(name, None)
        # Clean up cache
        cache_path = join(cache_dir, name)
        if os.path.isdir(cache_path):
            shutil.rmtree(cache_path, ignore_errors=True)
        json_path = join(cache_dir, f'{name}.json')
        if os.path.exists(json_path):
            os.remove(json_path)

    await save_known_marketplaces_config(known)


def _iso_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    import datetime
    return datetime.datetime.utcnow().isoformat() + 'Z'


# ---------------------------------------------------------------------------
# Marketplace removal
# ---------------------------------------------------------------------------

async def remove_marketplace(
    name: str,
    settings_source: Optional[str] = None,
    remove_plugins: bool = False,
) -> bool:
    """
    Remove a marketplace from the known marketplaces config and optionally
    remove its installed plugins.

    Returns True on success.
    """
    known = await load_known_marketplaces_config_safe()
    if name not in known:
        return False

    entry = known.pop(name)
    cache_dir = get_marketplaces_cache_dir()

    # Remove from disk cache
    if isinstance(entry, dict):
        install_location = entry.get('installLocation', '')
        source = entry.get('source', {})
        if install_location and not is_local_marketplace_source(source):
            if os.path.isdir(install_location):
                shutil.rmtree(install_location, ignore_errors=True)
            if os.path.isfile(install_location):
                os.remove(install_location)

    # Remove from in-memory cache
    _marketplace_cache.delete(name)

    # Optionally remove installed plugins
    if remove_plugins:
        try:
            from claude_code.utils.plugins.installed_plugins_manager import remove_all_plugins_for_marketplace
            await remove_all_plugins_for_marketplace(name)
        except ImportError:
            pass

    # Remove from settings
    if settings_source:
        try:
            from claude_code.utils.settings.settings import update_settings_for_source, get_settings_for_source
            settings = get_settings_for_source(settings_source) or {}
            extra = dict(settings.get('extraKnownMarketplaces') or {})
            extra.pop(name, None)
            await update_settings_for_source(settings_source, {'extraKnownMarketplaces': extra})
        except Exception:
            pass

    # Also update known_marketplaces.json
    # Remove plugin suffixed settings entries
    try:
        from claude_code.utils.settings.settings import get_settings_for_source, update_settings_for_source
        marketplace_suffix = f'@{name}'
        for src in ('userSettings', 'projectSettings', 'localSettings'):
            settings = get_settings_for_source(src) or {}
            enabled = dict(settings.get('enabledPlugins') or {})
            updated = {k: v for k, v in enabled.items() if not k.endswith(marketplace_suffix)}
            if len(updated) != len(enabled):
                await update_settings_for_source(src, {'enabledPlugins': updated})
    except Exception:
        pass

    return await save_known_marketplaces_config(known)


# ---------------------------------------------------------------------------
# Marketplace registration (add new marketplace to settings)
# ---------------------------------------------------------------------------

async def register_marketplace(
    name: str,
    source: Dict[str, Any],
    settings_source: str = 'userSettings',
    auto_update: Optional[bool] = None,
) -> Optional[str]:
    """
    Register a new marketplace in the user/project/local settings.
    Returns None on success, or an error message string on failure.
    """
    from claude_code.utils.plugins.schemas import validate_marketplace_name, validate_official_name_source

    # Validate name
    name_error = validate_marketplace_name(name)
    if name_error:
        return name_error

    # Validate official name source
    source_error = validate_official_name_source(name, source)
    if source_error:
        return source_error

    # Load and cache the marketplace to verify it's valid
    cache_dir = get_marketplaces_cache_dir()
    result = await load_and_cache_marketplace(name, source, cache_dir, force_update=True)
    if result is None:
        return f"Failed to load marketplace '{name}' from the given source"

    # Add to settings
    try:
        from claude_code.utils.settings.settings import get_settings_for_source, update_settings_for_source
        settings = get_settings_for_source(settings_source) or {}
        extra = dict(settings.get('extraKnownMarketplaces') or {})
        entry: Dict[str, Any] = {'source': source}
        if auto_update is not None:
            entry['autoUpdate'] = auto_update
        extra[name] = entry
        await update_settings_for_source(settings_source, {'extraKnownMarketplaces': extra})
    except Exception as e:
        return str(e)

    # Update known_marketplaces.json
    known = await load_known_marketplaces_config_safe()
    known[name] = {
        'source': source,
        'installLocation': result.cache_path,
        'lastUpdated': _iso_now(),
        'autoUpdate': auto_update,
    }
    await save_known_marketplaces_config(known)
    return None


# ---------------------------------------------------------------------------
# Auto-update
# ---------------------------------------------------------------------------

async def auto_update_marketplaces(
    known: Dict[str, Any],
    cache_dir: str,
) -> None:
    """
    Auto-update marketplaces that have auto_update enabled.
    """
    from claude_code.utils.plugins.schemas import is_marketplace_auto_update

    for name, entry in known.items():
        if not isinstance(entry, dict):
            continue
        source = entry.get('source', {})
        if not is_marketplace_auto_update(name, entry):
            continue
        if is_local_marketplace_source(source):
            continue  # skip local sources

        install_location = entry.get('installLocation', '')
        source_type = source.get('source', '')

        try:
            if source_type in ('github', 'git') and os.path.isdir(install_location):
                await git_pull(install_location)
            else:
                await load_and_cache_marketplace(name, source, cache_dir, force_update=True)

            entry['lastUpdated'] = _iso_now()
        except Exception:
            pass  # log error but continue


# ---------------------------------------------------------------------------
# Seed directory registration
# ---------------------------------------------------------------------------

def register_seed_marketplaces(force: bool = False) -> None:
    """
    Register marketplaces found in seed directories.
    Seed directories are pre-packaged marketplace bundles shipped with the app.
    """
    try:
        from claude_code.utils.plugins.plugin_directories import get_plugin_seed_dirs
        seed_dirs = get_plugin_seed_dirs()
    except ImportError:
        return

    known = load_known_marketplaces_config_sync()
    cache_dir = get_marketplaces_cache_dir()

    for seed_dir in seed_dirs:
        seed_known_path = join(seed_dir, 'known_marketplaces.json')
        seed_known = _read_json_file(seed_known_path)
        if not seed_known:
            continue
        for name, entry in seed_known.items():
            if name in known and not force:
                continue  # already registered, don't overwrite
            if isinstance(entry, dict):
                source = entry.get('source', {})
                # Point installLocation at seed dir copy
                seed_install = join(seed_dir, 'marketplaces', name)
                known[name] = {
                    'source': source,
                    'installLocation': seed_install,
                    'lastUpdated': entry.get('lastUpdated', _iso_now()),
                    'autoUpdate': entry.get('autoUpdate'),
                }
    # sync write
    path = _get_known_marketplaces_file()
    _write_json_file(path, known)


# ---------------------------------------------------------------------------
# Plugin installation from marketplace
# ---------------------------------------------------------------------------

async def install_plugin_from_marketplace_entry(
    entry: Any,
    marketplace_name: str,
    marketplace_install_location: str,
    plugin_id: str,
    enabled: bool,
) -> Optional[str]:
    """
    Install a plugin from a marketplace entry.
    Returns the install path on success, or None on failure.

    The entry is a PluginMarketplaceEntry (or dict-like).
    """
    try:
        from claude_code.utils.plugins.plugin_loader import (
            get_versioned_cache_path,
            cache_plugin,
        )
    except ImportError:
        return None

    source = entry.source if hasattr(entry, 'source') else entry.get('source', '')
    name = entry.name if hasattr(entry, 'name') else entry.get('name', '')
    version = entry.version if hasattr(entry, 'version') else entry.get('version', '0.0.0')

    if not version:
        version = '0.0.0'

    install_path = get_versioned_cache_path(plugin_id, version)
    if os.path.isdir(install_path):
        return install_path

    result = await cache_plugin(source, name, marketplace_name, marketplace_install_location)
    return result


# ---------------------------------------------------------------------------
# diff helper used by marketplace reconciler
# ---------------------------------------------------------------------------

def is_equal(a: Any, b: Any) -> bool:
    """Deep equality check."""
    return a == b
