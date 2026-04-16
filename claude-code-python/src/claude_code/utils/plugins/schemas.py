"""Plugin schemas. Ported from utils/plugins/schemas.ts (1681 lines)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Set, Union


# ---------------------------------------------------------------------------
# Official marketplace names
# ---------------------------------------------------------------------------

ALLOWED_OFFICIAL_MARKETPLACE_NAMES: Set[str] = {
    'claude-code-marketplace',
    'claude-code-plugins',
    'claude-plugins-official',
    'anthropic-marketplace',
    'anthropic-plugins',
    'agent-skills',
    'life-sciences',
    'knowledge-work-plugins',
}

# Official marketplaces that should NOT auto-update by default.
_NO_AUTO_UPDATE_OFFICIAL_MARKETPLACES: Set[str] = {'knowledge-work-plugins'}


def is_marketplace_auto_update(marketplace_name: str, entry: Dict[str, Any]) -> bool:
    """
    Check if auto-update is enabled for a marketplace.

    Uses the stored value if set, otherwise defaults based on whether
    it's an official Anthropic marketplace (true) or not (false).
    Official marketplaces in NO_AUTO_UPDATE_OFFICIAL_MARKETPLACES are excluded
    from the auto-update default.
    """
    normalized_name = marketplace_name.lower()
    if 'autoUpdate' in entry and entry['autoUpdate'] is not None:
        return bool(entry['autoUpdate'])
    return (
        normalized_name in ALLOWED_OFFICIAL_MARKETPLACE_NAMES
        and normalized_name not in _NO_AUTO_UPDATE_OFFICIAL_MARKETPLACES
    )


# Pattern to detect names that impersonate official Anthropic/Claude marketplaces.
BLOCKED_OFFICIAL_NAME_PATTERN = re.compile(
    r'(?:official[^a-z0-9]*(anthropic|claude)|(?:anthropic|claude)[^a-z0-9]*official'
    r'|^(?:anthropic|claude)[^a-z0-9]*(marketplace|plugins|official))',
    re.IGNORECASE,
)

# Pattern to detect non-ASCII characters that could be used for homograph attacks.
_NON_ASCII_PATTERN = re.compile(r'[^\u0020-\u007E]')


def is_blocked_official_name(name: str) -> bool:
    """
    Check if a marketplace name impersonates an official Anthropic/Claude marketplace.

    Returns True if the name is blocked (impersonates official), False if allowed.
    """
    if name.lower() in ALLOWED_OFFICIAL_MARKETPLACE_NAMES:
        return False
    if _NON_ASCII_PATTERN.search(name):
        return True
    return bool(BLOCKED_OFFICIAL_NAME_PATTERN.search(name))


# The official GitHub organization for Anthropic marketplaces.
OFFICIAL_GITHUB_ORG = 'anthropics'


def validate_official_name_source(
    name: str,
    source: Dict[str, Any],
) -> Optional[str]:
    """
    Validate that a marketplace with a reserved name comes from the official source.

    Returns an error message if validation fails, or None if valid.
    """
    normalized_name = name.lower()

    if normalized_name not in ALLOWED_OFFICIAL_MARKETPLACE_NAMES:
        return None

    if source.get('source') == 'github':
        repo = source.get('repo', '')
        if not repo.lower().startswith(f'{OFFICIAL_GITHUB_ORG}/'):
            return (
                f"The name '{name}' is reserved for official Anthropic marketplaces. "
                f"Only repositories from 'github.com/{OFFICIAL_GITHUB_ORG}/' can use this name."
            )
        return None

    if source.get('source') == 'git' and source.get('url'):
        url = source['url'].lower()
        is_https_anthropics = 'github.com/anthropics/' in url
        is_ssh_anthropics = 'git@github.com:anthropics/' in url
        if is_https_anthropics or is_ssh_anthropics:
            return None
        return (
            f"The name '{name}' is reserved for official Anthropic marketplaces. "
            f"Only repositories from 'github.com/{OFFICIAL_GITHUB_ORG}/' can use this name."
        )

    return (
        f"The name '{name}' is reserved for official Anthropic marketplaces and can only be "
        f"used with GitHub sources from the '{OFFICIAL_GITHUB_ORG}' organization."
    )


def is_local_plugin_source(source: Any) -> bool:
    """
    Check if a plugin source is a local path (stored in marketplace directory).

    Local plugins have their source as a string starting with './' (relative to marketplace).
    External plugins have their source as an object (npm, pip, git, github, etc.).
    """
    return isinstance(source, str) and source.startswith('./')


def is_local_marketplace_source(source: Dict[str, Any]) -> bool:
    """
    Whether a marketplace source points at a user-controlled local filesystem path.

    Returns True for 'file' or 'directory' sources.
    """
    return source.get('source') in ('file', 'directory')


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_DEP_REF_REGEX = re.compile(
    r'^[a-z0-9][-a-z0-9._]*(@[a-z0-9][-a-z0-9._]*)?(@\^[^@]*)?$',
    re.IGNORECASE,
)

_GIT_SHA_PATTERN = re.compile(r'^[a-f0-9]{40}$')

_MARKETPLACE_NAME_SPACE_RE = re.compile(r' ')
_MARKETPLACE_NAME_PATH_RE = re.compile(r'[/\\]|\.\.')
_NPM_SCOPED_RE = re.compile(r'^@[a-z0-9][a-z0-9\-._]*/[a-z0-9][a-z0-9\-._]*$')
_NPM_REGULAR_RE = re.compile(r'^[a-z0-9][a-z0-9\-._]*$')
_OPTION_KEY_RE = re.compile(r'^[A-Za-z_]\w*$')
_PLUGIN_ID_RE = re.compile(r'^[a-z0-9][-a-z0-9._]*@[a-z0-9][-a-z0-9._]*$', re.IGNORECASE)
_PLUGIN_NAME_RE = re.compile(r'^[a-z0-9][-a-z0-9._]*$', re.IGNORECASE)


def validate_marketplace_name(name: str) -> Optional[str]:
    """Validate a marketplace name. Returns error string or None."""
    if not name:
        return 'Marketplace must have a name'
    if ' ' in name:
        return 'Marketplace name cannot contain spaces. Use kebab-case (e.g., "my-marketplace")'
    if '/' in name or '\\' in name or '..' in name or name == '.':
        return 'Marketplace name cannot contain path separators (/ or \\), ".." sequences, or be "."'
    if is_blocked_official_name(name):
        return 'Marketplace name impersonates an official Anthropic/Claude marketplace'
    if name.lower() == 'inline':
        return 'Marketplace name "inline" is reserved for --plugin-dir session plugins'
    if name.lower() == 'builtin':
        return 'Marketplace name "builtin" is reserved for built-in plugins'
    return None


def validate_plugin_id(plugin_id: str) -> bool:
    """Validate a plugin ID in format 'plugin@marketplace'."""
    return bool(_PLUGIN_ID_RE.match(plugin_id))


def validate_git_sha(sha: str) -> bool:
    """Validate a 40-character git commit SHA."""
    return len(sha) == 40 and bool(_GIT_SHA_PATTERN.match(sha))


def validate_npm_package_name(name: str) -> bool:
    """Validate an npm package name including scoped packages."""
    if '..' in name or '//' in name:
        return False
    return bool(_NPM_SCOPED_RE.match(name)) or bool(_NPM_REGULAR_RE.match(name))


def normalize_dependency_ref(dep: Any) -> Optional[str]:
    """
    Normalize a dependency reference to 'name' or 'name@marketplace' string.
    Returns None if invalid.
    """
    if isinstance(dep, str):
        if not _DEP_REF_REGEX.match(dep):
            return None
        # Strip trailing @^version if present
        return re.sub(r'@\^[^@]*$', '', dep)
    if isinstance(dep, dict):
        name = dep.get('name', '')
        marketplace = dep.get('marketplace')
        if not name or not _PLUGIN_NAME_RE.match(name):
            return None
        if marketplace:
            if not _PLUGIN_NAME_RE.match(marketplace):
                return None
            return f'{name}@{marketplace}'
        return name
    return None


# ---------------------------------------------------------------------------
# Dataclasses for schemas
# ---------------------------------------------------------------------------

@dataclass
class PluginAuthor:
    """Plugin author information."""
    name: str
    email: Optional[str] = None
    url: Optional[str] = None


@dataclass
class CommandMetadata:
    """Metadata for plugin command definitions."""
    source: Optional[str] = None   # relative path to markdown file
    content: Optional[str] = None  # inline markdown content
    description: Optional[str] = None
    argument_hint: Optional[str] = None
    model: Optional[str] = None
    allowed_tools: Optional[List[str]] = None


@dataclass
class LspServerConfig:
    """LSP server configuration."""
    command: str
    extension_to_language: Dict[str, str] = field(default_factory=dict)
    args: Optional[List[str]] = None
    transport: str = 'stdio'
    env: Optional[Dict[str, str]] = None
    initialization_options: Any = None
    settings: Any = None
    workspace_folder: Optional[str] = None
    startup_timeout: Optional[int] = None
    shutdown_timeout: Optional[int] = None
    restart_on_crash: Optional[bool] = None
    max_restarts: Optional[int] = None


@dataclass
class PluginUserConfigOption:
    """A single user-configurable option in plugin manifest userConfig."""
    type: str  # 'string'|'number'|'boolean'|'directory'|'file'
    title: str
    description: str
    required: Optional[bool] = None
    default: Any = None
    multiple: Optional[bool] = None
    sensitive: Optional[bool] = None
    min: Optional[float] = None
    max: Optional[float] = None


@dataclass
class PluginManifest:
    """Plugin manifest file (plugin.json)."""
    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    author: Optional[PluginAuthor] = None
    homepage: Optional[str] = None
    repository: Optional[str] = None
    license: Optional[str] = None
    keywords: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    hooks: Any = None
    commands: Any = None
    agents: Any = None
    skills: Any = None
    output_styles: Any = None
    channels: Optional[List[Dict[str, Any]]] = None
    mcp_servers: Any = None
    lsp_servers: Any = None
    settings: Optional[Dict[str, Any]] = None
    user_config: Optional[Dict[str, PluginUserConfigOption]] = None


# MarketplaceSource is a union of source-typed dicts
MarketplaceSource = Dict[str, Any]

# PluginSource is either a relative path string or a source-typed dict
PluginSource = Union[str, Dict[str, Any]]


@dataclass
class PluginMarketplaceEntry:
    """Individual plugin entry in a marketplace."""
    name: str
    source: PluginSource
    version: Optional[str] = None
    description: Optional[str] = None
    author: Optional[PluginAuthor] = None
    homepage: Optional[str] = None
    repository: Optional[str] = None
    license: Optional[str] = None
    keywords: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    strict: bool = True
    hooks: Any = None
    commands: Any = None
    agents: Any = None
    skills: Any = None
    mcp_servers: Any = None
    lsp_servers: Any = None
    settings: Optional[Dict[str, Any]] = None
    user_config: Optional[Dict[str, PluginUserConfigOption]] = None


@dataclass
class PluginMarketplaceMetadata:
    """Optional marketplace metadata."""
    plugin_root: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None


@dataclass
class PluginMarketplace:
    """Plugin marketplace configuration."""
    name: str
    owner: Optional[PluginAuthor]
    plugins: List[PluginMarketplaceEntry] = field(default_factory=list)
    force_remove_deleted_plugins: Optional[bool] = None
    metadata: Optional[PluginMarketplaceMetadata] = None
    allow_cross_marketplace_dependencies_on: Optional[List[str]] = None


@dataclass
class InstalledPlugin:
    """Installed plugin metadata (V1 format)."""
    version: str
    installed_at: str
    install_path: str
    last_updated: Optional[str] = None
    git_commit_sha: Optional[str] = None


@dataclass
class InstalledPluginsFileV1:
    """installed_plugins.json file (V1 format)."""
    version: int  # literal 1
    plugins: Dict[str, InstalledPlugin] = field(default_factory=dict)


@dataclass
class PluginInstallationEntry:
    """A single plugin installation entry (V2)."""
    scope: str  # 'managed'|'user'|'project'|'local'
    install_path: str
    project_path: Optional[str] = None
    version: Optional[str] = None
    installed_at: Optional[str] = None
    last_updated: Optional[str] = None
    git_commit_sha: Optional[str] = None


@dataclass
class InstalledPluginsFileV2:
    """installed_plugins.json file (V2 format)."""
    version: int  # literal 2
    plugins: Dict[str, List[PluginInstallationEntry]] = field(default_factory=dict)


@dataclass
class KnownMarketplace:
    """Known marketplace entry."""
    source: MarketplaceSource
    install_location: str
    last_updated: str
    auto_update: Optional[bool] = None


# KnownMarketplacesFile is a dict mapping marketplace name → KnownMarketplace
KnownMarketplacesFile = Dict[str, KnownMarketplace]


# ---------------------------------------------------------------------------
# Parsing helpers (JSON dict → dataclass)
# ---------------------------------------------------------------------------

def parse_plugin_author(data: Dict[str, Any]) -> PluginAuthor:
    return PluginAuthor(
        name=data.get('name', ''),
        email=data.get('email'),
        url=data.get('url'),
    )


def parse_lsp_server_config(data: Dict[str, Any]) -> LspServerConfig:
    return LspServerConfig(
        command=data.get('command', ''),
        extension_to_language=data.get('extensionToLanguage', {}),
        args=data.get('args'),
        transport=data.get('transport', 'stdio'),
        env=data.get('env'),
        initialization_options=data.get('initializationOptions'),
        settings=data.get('settings'),
        workspace_folder=data.get('workspaceFolder'),
        startup_timeout=data.get('startupTimeout'),
        shutdown_timeout=data.get('shutdownTimeout'),
        restart_on_crash=data.get('restartOnCrash'),
        max_restarts=data.get('maxRestarts'),
    )


def parse_user_config_option(data: Dict[str, Any]) -> PluginUserConfigOption:
    return PluginUserConfigOption(
        type=data.get('type', 'string'),
        title=data.get('title', ''),
        description=data.get('description', ''),
        required=data.get('required'),
        default=data.get('default'),
        multiple=data.get('multiple'),
        sensitive=data.get('sensitive'),
        min=data.get('min'),
        max=data.get('max'),
    )


def parse_plugin_manifest(data: Dict[str, Any]) -> PluginManifest:
    """Parse a plugin.json dict into a PluginManifest."""
    author = parse_plugin_author(data['author']) if 'author' in data and data['author'] else None
    user_config: Optional[Dict[str, PluginUserConfigOption]] = None
    if 'userConfig' in data and data['userConfig']:
        user_config = {k: parse_user_config_option(v) for k, v in data['userConfig'].items()}

    return PluginManifest(
        name=data.get('name', ''),
        version=data.get('version'),
        description=data.get('description'),
        author=author,
        homepage=data.get('homepage'),
        repository=data.get('repository'),
        license=data.get('license'),
        keywords=data.get('keywords'),
        dependencies=data.get('dependencies'),
        hooks=data.get('hooks'),
        commands=data.get('commands'),
        agents=data.get('agents'),
        skills=data.get('skills'),
        output_styles=data.get('outputStyles'),
        channels=data.get('channels'),
        mcp_servers=data.get('mcpServers'),
        lsp_servers=data.get('lspServers'),
        settings=data.get('settings'),
        user_config=user_config,
    )


def parse_marketplace_entry(data: Dict[str, Any]) -> PluginMarketplaceEntry:
    """Parse a marketplace plugin entry dict."""
    author = parse_plugin_author(data['author']) if 'author' in data and data['author'] else None
    user_config: Optional[Dict[str, PluginUserConfigOption]] = None
    if 'userConfig' in data and data['userConfig']:
        user_config = {k: parse_user_config_option(v) for k, v in data['userConfig'].items()}
    return PluginMarketplaceEntry(
        name=data.get('name', ''),
        source=data.get('source', ''),
        version=data.get('version'),
        description=data.get('description'),
        author=author,
        homepage=data.get('homepage'),
        repository=data.get('repository'),
        license=data.get('license'),
        keywords=data.get('keywords'),
        dependencies=data.get('dependencies'),
        category=data.get('category'),
        tags=data.get('tags'),
        strict=data.get('strict', True),
        hooks=data.get('hooks'),
        commands=data.get('commands'),
        agents=data.get('agents'),
        skills=data.get('skills'),
        mcp_servers=data.get('mcpServers'),
        lsp_servers=data.get('lspServers'),
        settings=data.get('settings'),
        user_config=user_config,
    )


def parse_plugin_marketplace(data: Dict[str, Any]) -> PluginMarketplace:
    """Parse a marketplace.json dict into a PluginMarketplace."""
    owner = parse_plugin_author(data['owner']) if 'owner' in data and data['owner'] else None
    plugins = [parse_marketplace_entry(p) for p in data.get('plugins', [])]
    metadata: Optional[PluginMarketplaceMetadata] = None
    if 'metadata' in data and data['metadata']:
        m = data['metadata']
        metadata = PluginMarketplaceMetadata(
            plugin_root=m.get('pluginRoot'),
            version=m.get('version'),
            description=m.get('description'),
        )
    return PluginMarketplace(
        name=data.get('name', ''),
        owner=owner,
        plugins=plugins,
        force_remove_deleted_plugins=data.get('forceRemoveDeletedPlugins'),
        metadata=metadata,
        allow_cross_marketplace_dependencies_on=data.get('allowCrossMarketplaceDependenciesOn'),
    )


def parse_installed_plugin(data: Dict[str, Any]) -> InstalledPlugin:
    return InstalledPlugin(
        version=data.get('version', ''),
        installed_at=data.get('installedAt', ''),
        install_path=data.get('installPath', ''),
        last_updated=data.get('lastUpdated'),
        git_commit_sha=data.get('gitCommitSha'),
    )


def parse_plugin_installation_entry(data: Dict[str, Any]) -> PluginInstallationEntry:
    return PluginInstallationEntry(
        scope=data.get('scope', 'user'),
        install_path=data.get('installPath', ''),
        project_path=data.get('projectPath'),
        version=data.get('version'),
        installed_at=data.get('installedAt'),
        last_updated=data.get('lastUpdated'),
        git_commit_sha=data.get('gitCommitSha'),
    )


def parse_installed_plugins_file(
    data: Dict[str, Any],
) -> Union[InstalledPluginsFileV1, InstalledPluginsFileV2]:
    """Parse installed_plugins.json (V1 or V2 format)."""
    version = data.get('version', 1)
    plugins_raw = data.get('plugins', {})
    if version == 1:
        plugins: Dict[str, InstalledPlugin] = {
            k: parse_installed_plugin(v) for k, v in plugins_raw.items()
        }
        return InstalledPluginsFileV1(version=1, plugins=plugins)
    # V2
    plugins_v2: Dict[str, List[PluginInstallationEntry]] = {
        k: [parse_plugin_installation_entry(e) for e in v]
        for k, v in plugins_raw.items()
    }
    return InstalledPluginsFileV2(version=2, plugins=plugins_v2)


def parse_known_marketplace(data: Dict[str, Any]) -> KnownMarketplace:
    return KnownMarketplace(
        source=data.get('source', {}),
        install_location=data.get('installLocation', ''),
        last_updated=data.get('lastUpdated', ''),
        auto_update=data.get('autoUpdate'),
    )


def parse_known_marketplaces_file(data: Dict[str, Any]) -> KnownMarketplacesFile:
    return {k: parse_known_marketplace(v) for k, v in data.items()}


# ---------------------------------------------------------------------------
# Type aliases (for TypeScript type compatibility)
# ---------------------------------------------------------------------------

PluginId = str  # "plugin-name@marketplace-name"
PluginManifestChannel = Dict[str, Any]
PluginScope = Literal['managed', 'user', 'project', 'local']
InstalledPluginsFile = Union[InstalledPluginsFileV1, InstalledPluginsFileV2]
