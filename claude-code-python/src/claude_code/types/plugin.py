"""
Plugin type definitions
原始 TS: src/types/plugin.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Union

# ---------------------------------------------------------------------------
# BuiltinPluginDefinition
# ---------------------------------------------------------------------------

@dataclass
class BuiltinPluginDefinition:
    name: str
    description: str
    version: Optional[str] = None
    skills: Optional[list[Any]] = None          # BundledSkillDefinition[]
    hooks: Optional[Any] = None                 # HooksSettings
    mcp_servers: Optional[dict[str, Any]] = None  # Record<string, McpServerConfig>
    is_available: Optional[Callable[[], bool]] = None
    default_enabled: Optional[bool] = None


@dataclass
class PluginRepository:
    url: str
    branch: str
    last_updated: Optional[str] = None
    commit_sha: Optional[str] = None


@dataclass
class PluginConfig:
    repositories: dict[str, PluginRepository] = field(default_factory=dict)


@dataclass
class LoadedPlugin:
    name: str
    manifest: Any                      # PluginManifest
    path: str
    source: str
    repository: str
    enabled: Optional[bool] = None
    is_builtin: Optional[bool] = None
    sha: Optional[str] = None
    commands_path: Optional[str] = None
    commands_paths: Optional[list[str]] = None
    commands_metadata: Optional[dict[str, Any]] = None
    agents_path: Optional[str] = None
    agents_paths: Optional[list[str]] = None
    skills_path: Optional[str] = None
    skills_paths: Optional[list[str]] = None
    output_styles_path: Optional[str] = None
    output_styles_paths: Optional[list[str]] = None
    hooks_config: Optional[Any] = None          # HooksSettings
    mcp_servers: Optional[dict[str, Any]] = None
    lsp_servers: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None


PluginComponent = Literal[
    "commands",
    "agents",
    "skills",
    "hooks",
    "output-styles",
]


# ---------------------------------------------------------------------------
# PluginError (discriminated union)
# ---------------------------------------------------------------------------

@dataclass
class PluginErrorPathNotFound:
    type: Literal["path-not-found"] = "path-not-found"
    source: str = ""
    plugin: Optional[str] = None
    path: str = ""
    component: PluginComponent = "commands"


@dataclass
class PluginErrorGitAuthFailed:
    type: Literal["git-auth-failed"] = "git-auth-failed"
    source: str = ""
    plugin: Optional[str] = None
    git_url: str = ""
    auth_type: Literal["ssh", "https"] = "https"


@dataclass
class PluginErrorGitTimeout:
    type: Literal["git-timeout"] = "git-timeout"
    source: str = ""
    plugin: Optional[str] = None
    git_url: str = ""
    operation: Literal["clone", "pull"] = "clone"


@dataclass
class PluginErrorNetworkError:
    type: Literal["network-error"] = "network-error"
    source: str = ""
    plugin: Optional[str] = None
    url: str = ""
    details: Optional[str] = None


@dataclass
class PluginErrorManifestParseError:
    type: Literal["manifest-parse-error"] = "manifest-parse-error"
    source: str = ""
    plugin: Optional[str] = None
    manifest_path: str = ""
    parse_error: str = ""


@dataclass
class PluginErrorManifestValidationError:
    type: Literal["manifest-validation-error"] = "manifest-validation-error"
    source: str = ""
    plugin: Optional[str] = None
    manifest_path: str = ""
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class PluginErrorPluginNotFound:
    type: Literal["plugin-not-found"] = "plugin-not-found"
    source: str = ""
    plugin_id: str = ""
    marketplace: str = ""


@dataclass
class PluginErrorMarketplaceNotFound:
    type: Literal["marketplace-not-found"] = "marketplace-not-found"
    source: str = ""
    marketplace: str = ""
    available_marketplaces: list[str] = field(default_factory=list)


@dataclass
class PluginErrorMarketplaceLoadFailed:
    type: Literal["marketplace-load-failed"] = "marketplace-load-failed"
    source: str = ""
    marketplace: str = ""
    reason: str = ""


@dataclass
class PluginErrorMcpConfigInvalid:
    type: Literal["mcp-config-invalid"] = "mcp-config-invalid"
    source: str = ""
    plugin: str = ""
    server_name: str = ""
    validation_error: str = ""


@dataclass
class PluginErrorMcpServerSuppressedDuplicate:
    type: Literal["mcp-server-suppressed-duplicate"] = "mcp-server-suppressed-duplicate"
    source: str = ""
    plugin: str = ""
    server_name: str = ""
    duplicate_of: str = ""


@dataclass
class PluginErrorLspConfigInvalid:
    type: Literal["lsp-config-invalid"] = "lsp-config-invalid"
    source: str = ""
    plugin: str = ""
    server_name: str = ""
    validation_error: str = ""


@dataclass
class PluginErrorHookLoadFailed:
    type: Literal["hook-load-failed"] = "hook-load-failed"
    source: str = ""
    plugin: str = ""
    hook_path: str = ""
    reason: str = ""


@dataclass
class PluginErrorComponentLoadFailed:
    type: Literal["component-load-failed"] = "component-load-failed"
    source: str = ""
    plugin: str = ""
    component: PluginComponent = "commands"
    path: str = ""
    reason: str = ""


@dataclass
class PluginErrorMcpbDownloadFailed:
    type: Literal["mcpb-download-failed"] = "mcpb-download-failed"
    source: str = ""
    plugin: str = ""
    url: str = ""
    reason: str = ""


@dataclass
class PluginErrorMcpbExtractFailed:
    type: Literal["mcpb-extract-failed"] = "mcpb-extract-failed"
    source: str = ""
    plugin: str = ""
    mcpb_path: str = ""
    reason: str = ""


@dataclass
class PluginErrorMcpbInvalidManifest:
    type: Literal["mcpb-invalid-manifest"] = "mcpb-invalid-manifest"
    source: str = ""
    plugin: str = ""
    mcpb_path: str = ""
    validation_error: str = ""


@dataclass
class PluginErrorLspServerStartFailed:
    type: Literal["lsp-server-start-failed"] = "lsp-server-start-failed"
    source: str = ""
    plugin: str = ""
    server_name: str = ""
    reason: str = ""


@dataclass
class PluginErrorLspServerCrashed:
    type: Literal["lsp-server-crashed"] = "lsp-server-crashed"
    source: str = ""
    plugin: str = ""
    server_name: str = ""
    exit_code: Optional[int] = None
    signal: Optional[str] = None


@dataclass
class PluginErrorLspRequestTimeout:
    type: Literal["lsp-request-timeout"] = "lsp-request-timeout"
    source: str = ""
    plugin: str = ""
    server_name: str = ""
    method: str = ""
    timeout_ms: int = 0


@dataclass
class PluginErrorLspRequestFailed:
    type: Literal["lsp-request-failed"] = "lsp-request-failed"
    source: str = ""
    plugin: str = ""
    server_name: str = ""
    method: str = ""
    error: str = ""


@dataclass
class PluginErrorMarketplaceBlockedByPolicy:
    type: Literal["marketplace-blocked-by-policy"] = "marketplace-blocked-by-policy"
    source: str = ""
    plugin: Optional[str] = None
    marketplace: str = ""
    blocked_by_blocklist: Optional[bool] = None
    allowed_sources: list[str] = field(default_factory=list)


@dataclass
class PluginErrorDependencyUnsatisfied:
    type: Literal["dependency-unsatisfied"] = "dependency-unsatisfied"
    source: str = ""
    plugin: str = ""
    dependency: str = ""
    reason: Literal["not-enabled", "not-found"] = "not-found"


@dataclass
class PluginErrorPluginCacheMiss:
    type: Literal["plugin-cache-miss"] = "plugin-cache-miss"
    source: str = ""
    plugin: str = ""
    install_path: str = ""


@dataclass
class PluginErrorGeneric:
    type: Literal["generic-error"] = "generic-error"
    source: str = ""
    plugin: Optional[str] = None
    error: str = ""


PluginError = Union[
    PluginErrorPathNotFound,
    PluginErrorGitAuthFailed,
    PluginErrorGitTimeout,
    PluginErrorNetworkError,
    PluginErrorManifestParseError,
    PluginErrorManifestValidationError,
    PluginErrorPluginNotFound,
    PluginErrorMarketplaceNotFound,
    PluginErrorMarketplaceLoadFailed,
    PluginErrorMcpConfigInvalid,
    PluginErrorMcpServerSuppressedDuplicate,
    PluginErrorLspConfigInvalid,
    PluginErrorHookLoadFailed,
    PluginErrorComponentLoadFailed,
    PluginErrorMcpbDownloadFailed,
    PluginErrorMcpbExtractFailed,
    PluginErrorMcpbInvalidManifest,
    PluginErrorLspServerStartFailed,
    PluginErrorLspServerCrashed,
    PluginErrorLspRequestTimeout,
    PluginErrorLspRequestFailed,
    PluginErrorMarketplaceBlockedByPolicy,
    PluginErrorDependencyUnsatisfied,
    PluginErrorPluginCacheMiss,
    PluginErrorGeneric,
]


@dataclass
class PluginLoadResult:
    enabled: list[LoadedPlugin] = field(default_factory=list)
    disabled: list[LoadedPlugin] = field(default_factory=list)
    errors: list[PluginError] = field(default_factory=list)


def get_plugin_error_message(error: PluginError) -> str:
    """Helper to get a display message from any PluginError."""
    t = error.type
    if t == "generic-error":
        return error.error  # type: ignore[union-attr]
    if t == "path-not-found":
        e = error  # type: ignore[assignment]
        return f"Path not found: {e.path} ({e.component})"
    if t == "git-auth-failed":
        e = error  # type: ignore[assignment]
        return f"Git authentication failed ({e.auth_type}): {e.git_url}"
    if t == "git-timeout":
        e = error  # type: ignore[assignment]
        return f"Git {e.operation} timeout: {e.git_url}"
    if t == "network-error":
        e = error  # type: ignore[assignment]
        details = f" - {e.details}" if e.details else ""
        return f"Network error: {e.url}{details}"
    if t == "manifest-parse-error":
        e = error  # type: ignore[assignment]
        return f"Manifest parse error: {e.parse_error}"
    if t == "manifest-validation-error":
        e = error  # type: ignore[assignment]
        return f"Manifest validation failed: {', '.join(e.validation_errors)}"
    if t == "plugin-not-found":
        e = error  # type: ignore[assignment]
        return f"Plugin {e.plugin_id} not found in marketplace {e.marketplace}"
    if t == "marketplace-not-found":
        e = error  # type: ignore[assignment]
        return f"Marketplace {e.marketplace} not found"
    if t == "marketplace-load-failed":
        e = error  # type: ignore[assignment]
        return f"Marketplace {e.marketplace} failed to load: {e.reason}"
    if t == "mcp-config-invalid":
        e = error  # type: ignore[assignment]
        return f"MCP server {e.server_name} invalid: {e.validation_error}"
    if t == "mcp-server-suppressed-duplicate":
        e = error  # type: ignore[assignment]
        if e.duplicate_of.startswith("plugin:"):
            parts = e.duplicate_of.split(":")
            dup_name = parts[1] if len(parts) > 1 else "?"
            dup = f'server provided by plugin "{dup_name}"'
        else:
            dup = f'already-configured "{e.duplicate_of}"'
        return f'MCP server "{e.server_name}" skipped — same command/URL as {dup}'
    if t == "hook-load-failed":
        e = error  # type: ignore[assignment]
        return f"Hook load failed: {e.reason}"
    if t == "component-load-failed":
        e = error  # type: ignore[assignment]
        return f"{e.component} load failed from {e.path}: {e.reason}"
    if t == "mcpb-download-failed":
        e = error  # type: ignore[assignment]
        return f"Failed to download MCPB from {e.url}: {e.reason}"
    if t == "mcpb-extract-failed":
        e = error  # type: ignore[assignment]
        return f"Failed to extract MCPB {e.mcpb_path}: {e.reason}"
    if t == "mcpb-invalid-manifest":
        e = error  # type: ignore[assignment]
        return f"MCPB manifest invalid at {e.mcpb_path}: {e.validation_error}"
    if t == "lsp-config-invalid":
        e = error  # type: ignore[assignment]
        return f'Plugin "{e.plugin}" has invalid LSP server config for "{e.server_name}": {e.validation_error}'
    if t == "lsp-server-start-failed":
        e = error  # type: ignore[assignment]
        return f'Plugin "{e.plugin}" failed to start LSP server "{e.server_name}": {e.reason}'
    if t == "lsp-server-crashed":
        e = error  # type: ignore[assignment]
        if e.signal:
            return f'Plugin "{e.plugin}" LSP server "{e.server_name}" crashed with signal {e.signal}'
        ec = e.exit_code if e.exit_code is not None else "unknown"
        return f'Plugin "{e.plugin}" LSP server "{e.server_name}" crashed with exit code {ec}'
    if t == "lsp-request-timeout":
        e = error  # type: ignore[assignment]
        return f'Plugin "{e.plugin}" LSP server "{e.server_name}" timed out on {e.method} request after {e.timeout_ms}ms'
    if t == "lsp-request-failed":
        e = error  # type: ignore[assignment]
        return f'Plugin "{e.plugin}" LSP server "{e.server_name}" {e.method} request failed: {e.error}'
    if t == "marketplace-blocked-by-policy":
        e = error  # type: ignore[assignment]
        if e.blocked_by_blocklist:
            return f"Marketplace '{e.marketplace}' is blocked by enterprise policy"
        return f"Marketplace '{e.marketplace}' is not in the allowed marketplace list"
    if t == "dependency-unsatisfied":
        e = error  # type: ignore[assignment]
        if e.reason == "not-enabled":
            hint = "disabled — enable it or remove the dependency"
        else:
            hint = "not found in any configured marketplace"
        return f'Dependency "{e.dependency}" is {hint}'
    if t == "plugin-cache-miss":
        e = error  # type: ignore[assignment]
        return f'Plugin "{e.plugin}" not cached at {e.install_path} — run /plugins to refresh'
    return f"Unknown plugin error: {t}"
