"""
Plugin Loader Module.
Ported from utils/plugins/pluginLoader.ts (3302 lines).

This module is responsible for discovering, loading, and validating Claude Code plugins.
It handles:
- Installing plugins from various sources (npm, pip, git, github, local)
- Loading plugin manifests (plugin.json)
- Discovering plugin components (commands, agents, skills, hooks, MCP servers, LSP servers)
- Managing the plugin cache directory
- Validating plugin configurations
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from os.path import basename, dirname, join
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass

try:
    from claude_code.utils.plugins.schemas import (
        CommandMetadata,
        PluginManifest,
        PluginMarketplaceEntry,
        PluginSource,
        is_local_plugin_source,
        parse_marketplace_entry,
        parse_plugin_manifest,
        validate_marketplace_name,
    )
except ImportError:
    pass  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLUGIN_MANIFEST_FILENAME = 'plugin.json'
PLUGIN_HOOKS_DIR = 'hooks'
PLUGIN_HOOKS_FILENAME = 'hooks.json'
PLUGIN_COMMANDS_DIR = 'commands'
PLUGIN_AGENTS_DIR = 'agents'
PLUGIN_SKILLS_DIR = 'skills'
PLUGIN_OUTPUT_STYLES_DIR = 'output-styles'
PLUGIN_MCP_CONFIG_FILENAME = '.mcp.json'
PLUGIN_LSP_CONFIG_FILENAME = '.lsp.json'
PLUGIN_CACHE_DIR_NAME = 'installed'

# Placeholder version used when no version is available
UNKNOWN_VERSION = '0.0.0'


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PluginError:
    """An error encountered while loading a plugin."""
    type: str  # 'path-not-found'|'invalid-manifest'|'generic-error'|etc.
    source: str  # plugin_id or marketplace
    plugin: str = ''
    path: str = ''
    component: str = ''
    error: str = ''


@dataclass
class LoadedPlugin:
    """
    A fully loaded and validated plugin, ready for use by the system.
    """
    id: str  # 'plugin-name@marketplace-name'
    name: str
    marketplace_name: str
    install_path: str
    manifest: Optional[Any] = None  # PluginManifest
    enabled: bool = True

    # Component paths
    commands_paths: Optional[List[str]] = None
    commands_metadata: Optional[Dict[str, Any]] = None
    agents_paths: Optional[List[str]] = None
    skills_paths: Optional[List[str]] = None
    output_styles_paths: Optional[List[str]] = None
    hooks_config: Any = None
    mcp_servers_config: Optional[Dict[str, Any]] = None
    lsp_servers_config: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None

    # Errors encountered during loading
    errors: List[PluginError] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Plugin directory helpers
# ---------------------------------------------------------------------------

def get_plugins_directory() -> str:
    """Get the base plugins directory path."""
    try:
        from claude_code.utils.plugins.plugin_directories import get_plugins_directory as _gpd
        return _gpd()
    except ImportError:
        home = os.environ.get('HOME', os.path.expanduser('~'))
        return join(home, '.claude', 'plugins')


def get_plugin_install_directory() -> str:
    """Get the directory where plugins are installed."""
    return join(get_plugins_directory(), PLUGIN_CACHE_DIR_NAME)


def get_plugin_cache_path(marketplace_name: str) -> str:
    """Get the cache path for a marketplace's plugins."""
    return join(get_plugin_install_directory(), marketplace_name)


def get_plugin_path(marketplace_name: str, plugin_name: str) -> str:
    """
    Get the path for a specific plugin within a marketplace's cache directory.
    Sanitizes plugin_name to be filesystem-safe.
    """
    cache_path = get_plugin_cache_path(marketplace_name)
    safe_name = re.sub(r'[^a-zA-Z0-9\-_]', '-', plugin_name)
    return join(cache_path, safe_name)


def get_versioned_cache_path(plugin_id: str, version: str) -> str:
    """
    Get the versioned cache path for a plugin installation.
    Format: <install_dir>/<marketplace>/<plugin_name>@<version>
    """
    if '@' not in plugin_id:
        return join(get_plugin_install_directory(), plugin_id, version)
    plugin_name, marketplace_name = plugin_id.rsplit('@', 1)
    safe_name = re.sub(r'[^a-zA-Z0-9\-_]', '-', plugin_name)
    safe_version = re.sub(r'[^a-zA-Z0-9\-_.]', '-', version)
    return join(get_plugin_install_directory(), marketplace_name, f'{safe_name}@{safe_version}')


def _make_temp_name(source: Dict[str, Any]) -> str:
    """Generate a temp directory name for a plugin source during installation."""
    import time
    timestamp = int(time.time() * 1000)
    source_type = source.get('source', 'unknown') if isinstance(source, dict) else 'path'
    prefixes: Dict[str, str] = {
        'npm': 'npm',
        'pip': 'pip',
        'github': 'git',
        'git': 'git',
        'git-subdir': 'git',
        'url': 'git',
        'file': 'local',
        'directory': 'local',
    }
    prefix = prefixes.get(source_type, 'unknown')
    return f'temp_{prefix}_{timestamp}_{os.getpid()}'


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

async def path_exists(path: str) -> bool:
    """Async check if a path exists."""
    return os.path.exists(path)


async def is_directory(path: str) -> bool:
    """Async check if a path is a directory."""
    return os.path.isdir(path)


def _read_json_file(path: str) -> Optional[Dict[str, Any]]:
    """Read and parse a JSON file. Returns None on error."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_file(path: str, data: Any) -> bool:
    """Write data as JSON to path."""
    try:
        os.makedirs(dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False


async def _exec_no_throw(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, str]:
    """Execute a command, returning (returncode, stdout, stderr)."""
    try:
        merged_env = {**os.environ, **(env or {})} if env else None
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=merged_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode('utf-8', errors='replace'), stderr.decode('utf-8', errors='replace')
    except Exception as e:
        return 1, '', str(e)


# ---------------------------------------------------------------------------
# Plugin installation from sources
# ---------------------------------------------------------------------------

async def cache_plugin(
    source: PluginSource,
    plugin_name: str,
    marketplace_name: str,
    marketplace_install_location: str,
) -> Optional[str]:
    """
    Install a plugin from its source into the cache directory.
    Returns the install path on success, or None on failure.
    """
    install_base = get_plugin_cache_path(marketplace_name)
    os.makedirs(install_base, exist_ok=True)

    # Local path relative to marketplace
    if is_local_plugin_source(source):
        assert isinstance(source, str)
        plugin_path = os.path.normpath(join(marketplace_install_location, source))
        if os.path.isdir(plugin_path):
            return plugin_path
        return None

    # External source object
    if not isinstance(source, dict):
        return None

    source_type = source.get('source', '')
    dest = get_plugin_path(marketplace_name, plugin_name)

    if source_type == 'npm':
        package = source.get('package', plugin_name)
        version = source.get('version', '')
        registry = source.get('registry')
        pkg_spec = f'{package}@{version}' if version else package
        cmd = ['npm', 'install', pkg_spec, '--prefix', dest]
        if registry:
            cmd += ['--registry', registry]
        os.makedirs(dest, exist_ok=True)
        rc, _, _ = await _exec_no_throw(cmd)
        if rc != 0:
            return None
        # npm installs to node_modules/<package>
        npm_plugin_path = join(dest, 'node_modules', package)
        return npm_plugin_path if os.path.isdir(npm_plugin_path) else dest

    elif source_type == 'pip':
        package = source.get('package', plugin_name)
        version_spec = source.get('version', '')
        registry = source.get('registry')
        pkg_spec = f'{package}{version_spec}' if version_spec else package
        cmd = ['pip', 'install', pkg_spec, '--target', dest]
        if registry:
            cmd += ['--index-url', registry]
        os.makedirs(dest, exist_ok=True)
        rc, _, _ = await _exec_no_throw(cmd)
        return dest if rc == 0 else None

    elif source_type in ('github', 'url', 'git'):
        if source_type == 'github':
            repo = source.get('repo', '')
            url = f'https://github.com/{repo}.git'
        else:
            url = source.get('url', '')

        ref = source.get('ref')
        sha = source.get('sha')

        # Clean up existing dest
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)

        cmd = ['git', 'clone', '--', url, dest]
        if ref and not sha:
            cmd = ['git', 'clone', '--branch', ref, '--', url, dest]

        rc, _, _ = await _exec_no_throw(cmd)
        if rc != 0:
            return None

        if sha:
            rc2, _, _ = await _exec_no_throw(['git', 'checkout', sha], cwd=dest)
            if rc2 != 0:
                return None

        return dest

    elif source_type == 'git-subdir':
        url = source.get('url', '')
        sub_path = source.get('path', '')
        ref = source.get('ref')
        sha = source.get('sha')

        # Use partial clone + sparse checkout to only materialize the subdirectory
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)

        clone_cmd = [
            'git', 'clone',
            '--filter=tree:0',
            '--sparse',
            '--',
            url, dest,
        ]
        if ref and not sha:
            clone_cmd = [
                'git', 'clone',
                '--filter=tree:0',
                '--sparse',
                '--branch', ref,
                '--',
                url, dest,
            ]

        rc, _, _ = await _exec_no_throw(clone_cmd)
        if rc != 0:
            return None

        if sha:
            await _exec_no_throw(['git', 'checkout', sha], cwd=dest)

        # sparse-checkout set
        if sub_path:
            await _exec_no_throw(
                ['git', 'sparse-checkout', 'set', '--cone', sub_path],
                cwd=dest,
            )
            subdir_path = join(dest, sub_path)
            return subdir_path if os.path.isdir(subdir_path) else dest

        return dest

    elif source_type == 'file':
        file_path = source.get('path', '')
        return file_path if os.path.exists(file_path) else None

    elif source_type == 'directory':
        dir_path = source.get('path', '')
        return dir_path if os.path.isdir(dir_path) else None

    return None


# ---------------------------------------------------------------------------
# Plugin manifest loading
# ---------------------------------------------------------------------------

def _read_plugin_manifest(plugin_path: str) -> Optional[Dict[str, Any]]:
    """Read and parse plugin.json from the plugin directory."""
    manifest_path = join(plugin_path, PLUGIN_MANIFEST_FILENAME)
    return _read_json_file(manifest_path)


def _has_plugin_manifest(plugin_path: str) -> bool:
    """Check if plugin.json exists in the plugin directory."""
    return os.path.isfile(join(plugin_path, PLUGIN_MANIFEST_FILENAME))


def _read_hooks_config(plugin_path: str) -> Optional[Dict[str, Any]]:
    """Read hooks.json from the plugin's hooks/ directory."""
    hooks_path = join(plugin_path, PLUGIN_HOOKS_DIR, PLUGIN_HOOKS_FILENAME)
    return _read_json_file(hooks_path)


def _read_mcp_config(plugin_path: str) -> Optional[Dict[str, Any]]:
    """Read .mcp.json from the plugin directory."""
    mcp_path = join(plugin_path, PLUGIN_MCP_CONFIG_FILENAME)
    return _read_json_file(mcp_path)


def _read_lsp_config(plugin_path: str) -> Optional[Dict[str, Any]]:
    """Read .lsp.json from the plugin directory."""
    lsp_path = join(plugin_path, PLUGIN_LSP_CONFIG_FILENAME)
    return _read_json_file(lsp_path)


# ---------------------------------------------------------------------------
# Component discovery
# ---------------------------------------------------------------------------

async def discover_plugin_commands(plugin_path: str) -> List[str]:
    """Discover command files in the plugin's commands/ directory."""
    commands_dir = join(plugin_path, PLUGIN_COMMANDS_DIR)
    if not os.path.isdir(commands_dir):
        return []
    paths = []
    for item in sorted(os.listdir(commands_dir)):
        full = join(commands_dir, item)
        if os.path.isfile(full) and item.endswith('.md'):
            paths.append(full)
        elif os.path.isdir(full) and os.path.isfile(join(full, 'SKILL.md')):
            # Skill directory used as command
            paths.append(full)
    return paths


async def discover_plugin_agents(plugin_path: str) -> List[str]:
    """Discover agent files in the plugin's agents/ directory."""
    agents_dir = join(plugin_path, PLUGIN_AGENTS_DIR)
    if not os.path.isdir(agents_dir):
        return []
    return sorted([
        join(agents_dir, f)
        for f in os.listdir(agents_dir)
        if f.endswith('.md') and os.path.isfile(join(agents_dir, f))
    ])


async def discover_plugin_skills(plugin_path: str) -> List[str]:
    """Discover skill directories in the plugin's skills/ directory."""
    skills_dir = join(plugin_path, PLUGIN_SKILLS_DIR)
    if not os.path.isdir(skills_dir):
        return []
    return sorted([
        join(skills_dir, d)
        for d in os.listdir(skills_dir)
        if os.path.isdir(join(skills_dir, d))
        and os.path.isfile(join(skills_dir, d, 'SKILL.md'))
    ])


async def discover_plugin_output_styles(plugin_path: str) -> List[str]:
    """Discover output style files/dirs in the plugin's output-styles/ directory."""
    styles_dir = join(plugin_path, PLUGIN_OUTPUT_STYLES_DIR)
    if not os.path.isdir(styles_dir):
        return []
    return sorted([
        join(styles_dir, item)
        for item in os.listdir(styles_dir)
        if os.path.exists(join(styles_dir, item))
    ])


# ---------------------------------------------------------------------------
# Path validation helper
# ---------------------------------------------------------------------------

async def validate_plugin_paths(
    relative_paths: List[str],
    plugin_path: str,
    plugin_name: str,
    plugin_id: str,
    component_type: str,
    component_label: str,
    context_msg: str,
    errors: List[PluginError],
) -> List[str]:
    """
    Validate a list of relative paths from a plugin entry.
    Returns the list of existing full paths.
    """
    checks = await asyncio.gather(*[
        _check_path(p, plugin_path)
        for p in relative_paths
    ])
    valid_paths = []
    for rp, (full_path, exists) in zip(relative_paths, checks):
        if exists:
            valid_paths.append(full_path)
        else:
            errors.append(PluginError(
                type='path-not-found',
                source=plugin_id,
                plugin=plugin_name,
                path=full_path,
                component=component_type,
            ))
    return valid_paths


async def _check_path(relative_path: str, base: str) -> Tuple[str, bool]:
    full = os.path.normpath(join(base, relative_path))
    return full, os.path.exists(full)


# ---------------------------------------------------------------------------
# Main plugin loading
# ---------------------------------------------------------------------------

async def create_plugin_from_path(
    plugin_path: str,
    plugin_id: str,
    marketplace_name: str,
    entry: Optional[Any] = None,
    enabled: bool = True,
) -> Optional[LoadedPlugin]:
    """
    Load and validate a plugin from its installed directory.

    Returns a LoadedPlugin on success, or None on fatal error.
    Errors that are non-fatal (e.g., missing optional components) are
    collected in the returned plugin's errors list.
    """
    errors: List[PluginError] = []
    plugin_name = plugin_id.split('@')[0] if '@' in plugin_id else plugin_id

    has_manifest = _has_plugin_manifest(plugin_path)
    raw_manifest: Optional[Dict[str, Any]] = None
    manifest: Optional[Any] = None

    if has_manifest:
        raw_manifest = _read_plugin_manifest(plugin_path)
        if raw_manifest is None:
            errors.append(PluginError(
                type='invalid-manifest',
                source=plugin_id,
                plugin=plugin_name,
                error='Failed to read or parse plugin.json',
            ))
            raw_manifest = {}

        # Validate name consistency
        manifest_name = raw_manifest.get('name', '')
        if manifest_name and manifest_name != plugin_name:
            errors.append(PluginError(
                type='invalid-manifest',
                source=plugin_id,
                plugin=plugin_name,
                error=f"Plugin name in plugin.json ({manifest_name!r}) doesn't match expected name ({plugin_name!r})",
            ))

        try:
            manifest = parse_plugin_manifest(raw_manifest)
        except Exception as e:
            errors.append(PluginError(
                type='invalid-manifest',
                source=plugin_id,
                plugin=plugin_name,
                error=str(e),
            ))

    # If strict mode and no manifest, fail
    strict = True
    if entry is not None:
        strict = getattr(entry, 'strict', True) if hasattr(entry, 'strict') else entry.get('strict', True)

    if strict and not has_manifest:
        errors.append(PluginError(
            type='invalid-manifest',
            source=plugin_id,
            plugin=plugin_name,
            error=f'Plugin {plugin_name} does not have a plugin.json (required in strict mode)',
        ))
        return None

    plugin = LoadedPlugin(
        id=plugin_id,
        name=plugin_name,
        marketplace_name=marketplace_name,
        install_path=plugin_path,
        manifest=manifest,
        enabled=enabled,
        errors=errors,
    )

    # Load hooks from hooks/hooks.json
    hooks_config = _read_hooks_config(plugin_path)
    if hooks_config:
        plugin.hooks_config = hooks_config

    # Load MCP servers from .mcp.json
    mcp_config = _read_mcp_config(plugin_path)
    if mcp_config and 'mcpServers' in mcp_config:
        plugin.mcp_servers_config = mcp_config['mcpServers']

    # Load LSP servers from .lsp.json
    lsp_config = _read_lsp_config(plugin_path)
    if lsp_config:
        plugin.lsp_servers_config = lsp_config

    # Discover standard component directories
    commands_paths, agents_paths, skills_paths, output_styles_paths = await asyncio.gather(
        discover_plugin_commands(plugin_path),
        discover_plugin_agents(plugin_path),
        discover_plugin_skills(plugin_path),
        discover_plugin_output_styles(plugin_path),
    )

    if commands_paths:
        plugin.commands_paths = commands_paths
    if agents_paths:
        plugin.agents_paths = agents_paths
    if skills_paths:
        plugin.skills_paths = skills_paths
    if output_styles_paths:
        plugin.output_styles_paths = output_styles_paths

    # Apply manifest overrides
    if manifest is not None and raw_manifest:
        _apply_manifest_components(plugin, manifest, raw_manifest, plugin_path, errors)

    # Apply marketplace entry overrides
    if entry is not None:
        await _apply_marketplace_entry_components(
            plugin, entry, plugin_path, plugin_id, has_manifest, errors
        )

    # Merge settings from manifest
    if manifest is not None and hasattr(manifest, 'settings') and manifest.settings:
        plugin.settings = _filter_allowlisted_settings(manifest.settings)

    # Merge settings from marketplace entry
    if entry is not None:
        entry_settings = (
            getattr(entry, 'settings', None) if hasattr(entry, 'settings')
            else (entry.get('settings') if isinstance(entry, dict) else None)
        )
        if entry_settings:
            allowed_entry_settings = _filter_allowlisted_settings(entry_settings)
            if plugin.settings:
                plugin.settings = {**allowed_entry_settings, **plugin.settings}
            else:
                plugin.settings = allowed_entry_settings

    return plugin


_ALLOWLISTED_SETTINGS_KEYS = frozenset({'agent'})


def _filter_allowlisted_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Filter settings to only include allowlisted keys."""
    return {k: v for k, v in settings.items() if k in _ALLOWLISTED_SETTINGS_KEYS}


def _apply_manifest_components(
    plugin: LoadedPlugin,
    manifest: Any,
    raw_manifest: Dict[str, Any],
    plugin_path: str,
    errors: List[PluginError],
) -> None:
    """Apply extra component paths from plugin.json manifest."""
    # Extra commands
    if hasattr(manifest, 'commands') and manifest.commands:
        _extend_list(plugin, 'commands_paths', _resolve_extra_paths(manifest.commands, plugin_path))
    # Extra agents
    if hasattr(manifest, 'agents') and manifest.agents:
        _extend_list(plugin, 'agents_paths', _resolve_extra_paths(manifest.agents, plugin_path))
    # Extra skills
    if hasattr(manifest, 'skills') and manifest.skills:
        _extend_list(plugin, 'skills_paths', _resolve_extra_paths(manifest.skills, plugin_path))
    # Extra output styles
    if hasattr(manifest, 'output_styles') and manifest.output_styles:
        _extend_list(plugin, 'output_styles_paths', _resolve_extra_paths(manifest.output_styles, plugin_path))
    # Inline hooks
    if hasattr(manifest, 'hooks') and manifest.hooks:
        plugin.hooks_config = manifest.hooks
    # Extra MCP servers (inline)
    if hasattr(manifest, 'mcp_servers') and manifest.mcp_servers:
        mcp = manifest.mcp_servers
        if isinstance(mcp, dict) and not _is_source_object(mcp):
            plugin.mcp_servers_config = {**(plugin.mcp_servers_config or {}), **mcp}


def _is_source_object(obj: Any) -> bool:
    """Check if an object is a source descriptor (has a 'source' key)."""
    return isinstance(obj, dict) and 'source' in obj


def _resolve_extra_paths(
    paths_spec: Any,
    plugin_path: str,
) -> List[str]:
    """Resolve extra paths from manifest (string, list, or object)."""
    if isinstance(paths_spec, str):
        full = os.path.normpath(join(plugin_path, paths_spec))
        return [full] if os.path.exists(full) else []
    if isinstance(paths_spec, list):
        result = []
        for p in paths_spec:
            if isinstance(p, str):
                full = os.path.normpath(join(plugin_path, p))
                if os.path.exists(full):
                    result.append(full)
        return result
    if isinstance(paths_spec, dict):
        # Object-mapping format for commands: {name: metadata}
        result = []
        for name, meta in paths_spec.items():
            if isinstance(meta, dict) and isinstance(meta.get('source'), str):
                full = os.path.normpath(join(plugin_path, meta['source']))
                if os.path.exists(full):
                    result.append(full)
        return result
    return []


def _extend_list(obj: Any, attr: str, items: List[str]) -> None:
    """Extend a list attribute on an object."""
    if not items:
        return
    existing = getattr(obj, attr, None) or []
    setattr(obj, attr, existing + items)


async def _apply_marketplace_entry_components(
    plugin: LoadedPlugin,
    entry: Any,
    plugin_path: str,
    plugin_id: str,
    has_manifest: bool,
    errors: List[PluginError],
) -> None:
    """
    Apply component overrides from a marketplace entry.

    When strict=True (default) and no plugin.json: marketplace entry IS the manifest.
    When strict=True and plugin.json exists: marketplace entry can supplement.
    When strict=False: marketplace entry supplements or is the only source.
    """
    strict = getattr(entry, 'strict', True) if hasattr(entry, 'strict') else entry.get('strict', True) if isinstance(entry, dict) else True

    def _get_entry(attr: str) -> Any:
        if hasattr(entry, attr):
            return getattr(entry, attr)
        if isinstance(entry, dict):
            return entry.get(attr)
        return None

    if strict and not has_manifest:
        # marketplace entry is the full manifest
        # Process commands
        commands_spec = _get_entry('commands')
        if commands_spec is not None:
            await _process_commands_from_entry(
                commands_spec, plugin, plugin_path, plugin_id,
                entry.name if hasattr(entry, 'name') else entry.get('name', ''),
                errors,
            )

        # Process agents
        agents_spec = _get_entry('agents')
        if agents_spec is not None:
            agent_paths_raw = agents_spec if isinstance(agents_spec, list) else [agents_spec]
            valid = await validate_plugin_paths(
                agent_paths_raw, plugin_path,
                entry.name if hasattr(entry, 'name') else entry.get('name', ''),
                plugin_id, 'agents', 'Agent', 'from marketplace entry', errors
            )
            if valid:
                plugin.agents_paths = (plugin.agents_paths or []) + valid

        # Process skills
        skills_spec = _get_entry('skills')
        if skills_spec is not None:
            skill_paths_raw = skills_spec if isinstance(skills_spec, list) else [skills_spec]
            valid = await validate_plugin_paths(
                skill_paths_raw, plugin_path,
                entry.name if hasattr(entry, 'name') else entry.get('name', ''),
                plugin_id, 'skills', 'Skill', 'from marketplace entry', errors
            )
            if valid:
                plugin.skills_paths = (plugin.skills_paths or []) + valid

        # Process output styles
        output_styles_spec = _get_entry('outputStyles') or _get_entry('output_styles')
        if output_styles_spec is not None:
            os_paths_raw = output_styles_spec if isinstance(output_styles_spec, list) else [output_styles_spec]
            valid = await validate_plugin_paths(
                os_paths_raw, plugin_path,
                entry.name if hasattr(entry, 'name') else entry.get('name', ''),
                plugin_id, 'output-styles', 'Output style', 'from marketplace entry', errors
            )
            if valid:
                plugin.output_styles_paths = (plugin.output_styles_paths or []) + valid

        # Inline hooks
        hooks_spec = _get_entry('hooks')
        if hooks_spec is not None:
            plugin.hooks_config = hooks_spec

        # Inline MCP servers
        mcp_servers_spec = _get_entry('mcpServers') or _get_entry('mcp_servers')
        if isinstance(mcp_servers_spec, dict) and not _is_source_object(mcp_servers_spec):
            plugin.mcp_servers_config = {**(plugin.mcp_servers_config or {}), **mcp_servers_spec}

        # Inline LSP servers
        lsp_servers_spec = _get_entry('lspServers') or _get_entry('lsp_servers')
        if isinstance(lsp_servers_spec, dict):
            plugin.lsp_servers_config = {**(plugin.lsp_servers_config or {}), **lsp_servers_spec}

    elif not strict and has_manifest and (
        _get_entry('commands') or _get_entry('agents') or _get_entry('skills')
        or _get_entry('hooks') or _get_entry('outputStyles') or _get_entry('output_styles')
    ):
        # Conflict: both plugin.json and marketplace entry have components
        errors.append(PluginError(
            type='generic-error',
            source=plugin_id,
            error=(
                f"Plugin {entry.name if hasattr(entry, 'name') else entry.get('name', '')} "
                f'has both plugin.json and marketplace manifest entries for '
                f'commands/agents/skills/hooks/outputStyles. This is a conflict.'
            ),
        ))

    elif has_manifest:
        # plugin.json exists — marketplace supplements it
        commands_spec = _get_entry('commands')
        if commands_spec is not None:
            await _process_commands_from_entry(
                commands_spec, plugin, plugin_path, plugin_id,
                entry.name if hasattr(entry, 'name') else entry.get('name', ''),
                errors,
            )

        agents_spec = _get_entry('agents')
        if agents_spec is not None:
            agent_paths_raw = agents_spec if isinstance(agents_spec, list) else [agents_spec]
            valid = await validate_plugin_paths(
                agent_paths_raw, plugin_path,
                entry.name if hasattr(entry, 'name') else entry.get('name', ''),
                plugin_id, 'agents', 'Agent', 'from marketplace entry', errors
            )
            if valid:
                plugin.agents_paths = (plugin.agents_paths or []) + valid

        skills_spec = _get_entry('skills')
        if skills_spec is not None:
            skill_paths_raw = skills_spec if isinstance(skills_spec, list) else [skills_spec]
            valid = await validate_plugin_paths(
                skill_paths_raw, plugin_path,
                entry.name if hasattr(entry, 'name') else entry.get('name', ''),
                plugin_id, 'skills', 'Skill', 'from marketplace entry', errors
            )
            if valid:
                plugin.skills_paths = (plugin.skills_paths or []) + valid

        output_styles_spec = _get_entry('outputStyles') or _get_entry('output_styles')
        if output_styles_spec is not None:
            os_paths_raw = output_styles_spec if isinstance(output_styles_spec, list) else [output_styles_spec]
            valid = await validate_plugin_paths(
                os_paths_raw, plugin_path,
                entry.name if hasattr(entry, 'name') else entry.get('name', ''),
                plugin_id, 'output-styles', 'Output style', 'from marketplace entry', errors
            )
            if valid:
                plugin.output_styles_paths = (plugin.output_styles_paths or []) + valid

        hooks_spec = _get_entry('hooks')
        if hooks_spec is not None:
            plugin.hooks_config = hooks_spec

        mcp_servers_spec = _get_entry('mcpServers') or _get_entry('mcp_servers')
        if isinstance(mcp_servers_spec, dict) and not _is_source_object(mcp_servers_spec):
            plugin.mcp_servers_config = {**(plugin.mcp_servers_config or {}), **mcp_servers_spec}


async def _process_commands_from_entry(
    commands_spec: Any,
    plugin: LoadedPlugin,
    plugin_path: str,
    plugin_id: str,
    plugin_name: str,
    errors: List[PluginError],
) -> None:
    """Process commands from a marketplace entry (path, list, or object-mapping)."""
    if isinstance(commands_spec, dict) and not isinstance(commands_spec, list):
        # Check if it's object-mapping format
        first_value = next(iter(commands_spec.values()), None)
        is_metadata_map = (
            first_value is not None
            and isinstance(first_value, dict)
            and ('source' in first_value or 'content' in first_value)
        )
        if is_metadata_map:
            # Object mapping: {name: CommandMetadata}
            commands_metadata: Dict[str, Any] = dict(plugin.commands_metadata or {})
            valid_paths: List[str] = []

            checks = await asyncio.gather(*[
                _check_path(meta.get('source', ''), plugin_path)
                for _, meta in commands_spec.items()
                if isinstance(meta, dict) and meta.get('source')
            ])

            check_iter = iter(checks)
            for command_name, metadata in commands_spec.items():
                if not isinstance(metadata, dict) or not metadata.get('source'):
                    continue
                full_path, exists = next(check_iter)
                if exists:
                    valid_paths.append(full_path)
                    commands_metadata[command_name] = metadata
                else:
                    errors.append(PluginError(
                        type='path-not-found',
                        source=plugin_id,
                        plugin=plugin_name,
                        path=full_path,
                        component='commands',
                    ))

            if valid_paths:
                plugin.commands_paths = (plugin.commands_paths or []) + valid_paths
                plugin.commands_metadata = commands_metadata
            return

    # Path or list of paths
    cmd_paths = commands_spec if isinstance(commands_spec, list) else [commands_spec]
    valid = await validate_plugin_paths(
        [p for p in cmd_paths if isinstance(p, str)],
        plugin_path, plugin_name, plugin_id,
        'commands', 'Command', 'from marketplace entry', errors,
    )
    if valid:
        plugin.commands_paths = (plugin.commands_paths or []) + valid


# ---------------------------------------------------------------------------
# High-level plugin loading from marketplace
# ---------------------------------------------------------------------------

async def load_plugin_from_marketplace_entry(
    entry: Any,
    marketplace_name: str,
    marketplace_install_location: str,
    plugin_id: str,
    enabled: bool = True,
) -> Optional[LoadedPlugin]:
    """
    Load a plugin given a marketplace entry.

    1. Determines the plugin source (local path or external)
    2. Caches the plugin if needed
    3. Loads and validates the plugin from its install path
    """
    source = getattr(entry, 'source', None) if hasattr(entry, 'source') else entry.get('source') if isinstance(entry, dict) else None
    plugin_name = getattr(entry, 'name', '') if hasattr(entry, 'name') else entry.get('name', '') if isinstance(entry, dict) else ''

    if source is None:
        return None

    # Resolve the plugin path
    if is_local_plugin_source(source):
        assert isinstance(source, str)
        plugin_path = os.path.normpath(join(marketplace_install_location, source))
    else:
        plugin_path = await cache_plugin(
            source, plugin_name, marketplace_name, marketplace_install_location
        )

    if plugin_path is None or not os.path.isdir(plugin_path):
        return None

    return await create_plugin_from_path(
        plugin_path, plugin_id, marketplace_name, entry, enabled
    )


async def load_plugins_from_marketplace(
    marketplace: Any,
    marketplace_name: str,
    marketplace_install_location: str,
    enabled_plugin_ids: Optional[Set[str]] = None,
) -> Tuple[List[LoadedPlugin], List[PluginError]]:
    """
    Load all plugins from a marketplace.

    enabled_plugin_ids: if provided, only load plugins in this set.
    Returns (loaded_plugins, global_errors).
    """
    plugins_data = (
        marketplace.plugins if hasattr(marketplace, 'plugins')
        else marketplace.get('plugins', [])
    )

    all_errors: List[PluginError] = []
    tasks = []

    for entry in plugins_data:
        entry_name = getattr(entry, 'name', '') if hasattr(entry, 'name') else entry.get('name', '')
        plugin_id = f'{entry_name}@{marketplace_name}'

        if enabled_plugin_ids is not None and plugin_id not in enabled_plugin_ids:
            continue

        enabled = enabled_plugin_ids is None or plugin_id in enabled_plugin_ids
        tasks.append(
            load_plugin_from_marketplace_entry(
                entry, marketplace_name, marketplace_install_location, plugin_id, enabled
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    loaded: List[LoadedPlugin] = []
    for result in results:
        if isinstance(result, Exception):
            all_errors.append(PluginError(
                type='generic-error',
                source=marketplace_name,
                error=str(result),
            ))
        elif result is not None:
            loaded.append(result)
            all_errors.extend(result.errors)

    return loaded, all_errors


# ---------------------------------------------------------------------------
# Inline plugin loading (--plugin-dir)
# ---------------------------------------------------------------------------

async def load_inline_plugin(
    plugin_path: str,
    plugin_name: str = 'inline',
) -> Optional[LoadedPlugin]:
    """
    Load a plugin directly from a local directory (e.g., from --plugin-dir).
    The marketplace name is 'inline'.
    """
    if not os.path.isdir(plugin_path):
        return None
    plugin_id = f'{plugin_name}@inline'
    return await create_plugin_from_path(
        plugin_path, plugin_id, 'inline', entry=None, enabled=True
    )


# ---------------------------------------------------------------------------
# Built-in plugin loading
# ---------------------------------------------------------------------------

async def load_builtin_plugins(
    builtin_paths: Optional[List[str]] = None,
) -> Tuple[List[LoadedPlugin], List[PluginError]]:
    """
    Load built-in plugins that ship with Claude Code.
    """
    if builtin_paths is None:
        # Try to find built-in plugin dirs
        try:
            from claude_code.utils.plugins.plugin_directories import get_builtin_plugin_dirs
            builtin_paths = get_builtin_plugin_dirs()
        except ImportError:
            return [], []

    all_errors: List[PluginError] = []
    plugins: List[LoadedPlugin] = []

    for plugin_path in builtin_paths:
        if not os.path.isdir(plugin_path):
            continue
        plugin_name = basename(plugin_path)
        plugin_id = f'{plugin_name}@builtin'
        result = await create_plugin_from_path(plugin_path, plugin_id, 'builtin', enabled=True)
        if result is not None:
            plugins.append(result)
            all_errors.extend(result.errors)

    return plugins, all_errors


# ---------------------------------------------------------------------------
# Installed plugins tracking
# ---------------------------------------------------------------------------

def get_installed_plugins_file_path() -> str:
    """Get the path to the installed_plugins.json file."""
    return join(get_plugins_directory(), 'installed_plugins.json')


def read_installed_plugins_file() -> Dict[str, Any]:
    """Read the installed_plugins.json file."""
    path = get_installed_plugins_file_path()
    data = _read_json_file(path)
    if not isinstance(data, dict):
        return {'version': 2, 'plugins': {}}
    return data


def write_installed_plugins_file(data: Dict[str, Any]) -> bool:
    """Write the installed_plugins.json file."""
    path = get_installed_plugins_file_path()
    return _write_json_file(path, data)


def record_plugin_installation(
    plugin_id: str,
    scope: str,
    install_path: str,
    version: Optional[str] = None,
    project_path: Optional[str] = None,
    git_commit_sha: Optional[str] = None,
) -> bool:
    """Record a plugin installation in installed_plugins.json."""
    import datetime
    data = read_installed_plugins_file()
    if data.get('version', 1) == 1:
        # Migrate to V2
        data = {'version': 2, 'plugins': {}}

    plugins = data.setdefault('plugins', {})
    entries = plugins.setdefault(plugin_id, [])

    # Remove existing entry for same scope/project
    entries[:] = [
        e for e in entries
        if not (e.get('scope') == scope and e.get('projectPath') == project_path)
    ]

    entry: Dict[str, Any] = {
        'scope': scope,
        'installPath': install_path,
        'installedAt': datetime.datetime.utcnow().isoformat() + 'Z',
    }
    if version:
        entry['version'] = version
    if project_path:
        entry['projectPath'] = project_path
    if git_commit_sha:
        entry['gitCommitSha'] = git_commit_sha

    entries.append(entry)
    return write_installed_plugins_file(data)


def remove_plugin_installation_record(
    plugin_id: str,
    scope: Optional[str] = None,
    project_path: Optional[str] = None,
) -> bool:
    """Remove a plugin installation record from installed_plugins.json."""
    data = read_installed_plugins_file()
    plugins = data.get('plugins', {})

    if plugin_id not in plugins:
        return True

    if scope is None:
        del plugins[plugin_id]
    else:
        entries = plugins[plugin_id]
        entries[:] = [
            e for e in entries
            if not (e.get('scope') == scope and e.get('projectPath') == project_path)
        ]
        if not entries:
            del plugins[plugin_id]

    return write_installed_plugins_file(data)


# ---------------------------------------------------------------------------
# Plugin settings schema filtering
# ---------------------------------------------------------------------------

def get_allowed_plugin_settings_keys() -> Set[str]:
    """
    Return the set of settings keys that plugins are allowed to set.
    Currently only 'agent' is allowlisted.
    """
    return _ALLOWLISTED_SETTINGS_KEYS


# ---------------------------------------------------------------------------
# Plugin update checking
# ---------------------------------------------------------------------------

async def check_plugin_version(
    plugin: LoadedPlugin,
    entry: Optional[Any] = None,
) -> Optional[str]:
    """
    Check if a newer version of the plugin is available.
    Returns the new version string if an update is available, or None.
    """
    if entry is None:
        return None
    entry_version = (
        getattr(entry, 'version', None) if hasattr(entry, 'version')
        else entry.get('version') if isinstance(entry, dict) else None
    )
    if not entry_version:
        return None
    manifest = plugin.manifest
    current_version = getattr(manifest, 'version', None) if manifest else None
    if not current_version:
        return None
    if entry_version != current_version:
        return entry_version
    return None


# ---------------------------------------------------------------------------
# Utility: flatten loaded plugins for API consumption
# ---------------------------------------------------------------------------

def flatten_plugins_for_context(
    loaded_plugins: List[LoadedPlugin],
) -> Dict[str, Any]:
    """
    Flatten loaded plugins into context-ready maps.
    Returns dicts suitable for use in ToolUseContext / AppState.
    """
    commands: Dict[str, Any] = {}
    agents: Dict[str, Any] = {}
    skills: Dict[str, Any] = {}
    mcp_servers: Dict[str, Any] = {}
    lsp_servers: Dict[str, Any] = {}
    settings_overrides: Dict[str, Any] = {}

    for plugin in loaded_plugins:
        if not plugin.enabled:
            continue

        namespace = plugin.name

        if plugin.commands_paths:
            for path in plugin.commands_paths:
                cmd_name = f'{namespace}:{basename(path).replace(".md", "")}'
                commands[cmd_name] = {
                    'path': path,
                    'pluginId': plugin.id,
                    'metadata': (plugin.commands_metadata or {}).get(basename(path).replace('.md', '')),
                }

        if plugin.agents_paths:
            for path in plugin.agents_paths:
                agent_name = f'{namespace}:{basename(path).replace(".md", "")}'
                agents[agent_name] = {'path': path, 'pluginId': plugin.id}

        if plugin.skills_paths:
            for path in plugin.skills_paths:
                skill_name = f'{namespace}:{basename(path)}'
                skills[skill_name] = {'path': path, 'pluginId': plugin.id}

        if plugin.mcp_servers_config:
            for server_name, config in plugin.mcp_servers_config.items():
                mcp_servers[f'{namespace}_{server_name}'] = config

        if plugin.lsp_servers_config:
            for server_name, config in plugin.lsp_servers_config.items():
                lsp_servers[f'{namespace}_{server_name}'] = config

        if plugin.settings:
            settings_overrides.update(plugin.settings)

    return {
        'commands': commands,
        'agents': agents,
        'skills': skills,
        'mcpServers': mcp_servers,
        'lspServers': lsp_servers,
        'settings': settings_overrides,
    }
