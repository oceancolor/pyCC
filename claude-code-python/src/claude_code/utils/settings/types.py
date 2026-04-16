"""
Settings types for Claude Code.
Python port of utils/settings/types.ts

Replaces Zod schemas with TypedDict and plain dict validation.
No third-party validation libraries required.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Union

# ---------------------------------------------------------------------------
# Re-exported for backward compatibility (from schemas/hooks equivalents)
# ---------------------------------------------------------------------------

# Hooks types (simplified Python equivalents)
HookCommand = Dict[str, Any]
HookMatcher = Dict[str, Any]
HooksSettings = Dict[str, Any]
AgentHook = Dict[str, Any]
BashCommandHook = Dict[str, Any]
HttpHook = Dict[str, Any]
PromptHook = Dict[str, Any]


# ---------------------------------------------------------------------------
# CUSTOMIZATION_SURFACES constant
# ---------------------------------------------------------------------------

CUSTOMIZATION_SURFACES = ("skills", "agents", "hooks", "mcp")
"""
Surfaces lockable by `strictPluginOnlyCustomization`. Exported so the
schema preprocessing and the runtime helper share one source of truth.
"""


# ---------------------------------------------------------------------------
# TypedDict / Dict-based type definitions
# ---------------------------------------------------------------------------

# EnvironmentVariablesSchema: record(str, coerce.str)
EnvironmentVariablesSchema = Dict[str, str]


class PermissionsSchema:
    """
    Schema for permissions section.
    allow/deny/ask: List of permission rule strings
    defaultMode: Optional permission mode string
    disableBypassPermissionsMode: Optional literal 'disable'
    additionalDirectories: Optional list of directory strings
    """
    allow: Optional[List[str]]
    deny: Optional[List[str]]
    ask: Optional[List[str]]
    defaultMode: Optional[str]
    disableBypassPermissionsMode: Optional[Literal["disable"]]
    additionalDirectories: Optional[List[str]]


# Using plain dicts for runtime usage
PermissionsDict = Dict[str, Any]


class ExtraKnownMarketplaceEntry:
    """Schema for extra marketplaces defined in repository settings."""
    source: Dict[str, Any]
    installLocation: Optional[str]
    autoUpdate: Optional[bool]


ExtraKnownMarketplaceDict = Dict[str, Any]


# ---------------------------------------------------------------------------
# AllowedMcpServerEntry
# ---------------------------------------------------------------------------

class AllowedMcpServerEntry:
    """
    Allowed MCP server entry in enterprise allowlist.
    Exactly one of serverName, serverCommand, or serverUrl must be set.
    """
    serverName: Optional[str]
    serverCommand: Optional[List[str]]
    serverUrl: Optional[str]


AllowedMcpServerEntryDict = Dict[str, Any]

# MCP server name regex pattern
_MCP_SERVER_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_allowed_mcp_server_entry(entry: Dict[str, Any]) -> bool:
    """
    Validate an AllowedMcpServerEntry dict.
    Returns True if valid (exactly one of serverName/serverCommand/serverUrl set).
    """
    defined_count = sum([
        entry.get("serverName") is not None,
        entry.get("serverCommand") is not None,
        entry.get("serverUrl") is not None,
    ])
    if defined_count != 1:
        return False
    if entry.get("serverName") is not None:
        if not isinstance(entry["serverName"], str):
            return False
        if not _MCP_SERVER_NAME_PATTERN.match(entry["serverName"]):
            return False
    if entry.get("serverCommand") is not None:
        if not isinstance(entry["serverCommand"], list) or len(entry["serverCommand"]) < 1:
            return False
    return True


# ---------------------------------------------------------------------------
# DeniedMcpServerEntry
# ---------------------------------------------------------------------------

class DeniedMcpServerEntry:
    """
    Denied MCP server entry in enterprise denylist.
    Exactly one of serverName, serverCommand, or serverUrl must be set.
    """
    serverName: Optional[str]
    serverCommand: Optional[List[str]]
    serverUrl: Optional[str]


DeniedMcpServerEntryDict = Dict[str, Any]


def validate_denied_mcp_server_entry(entry: Dict[str, Any]) -> bool:
    """
    Validate a DeniedMcpServerEntry dict.
    Returns True if valid (exactly one of serverName/serverCommand/serverUrl set).
    """
    defined_count = sum([
        entry.get("serverName") is not None,
        entry.get("serverCommand") is not None,
        entry.get("serverUrl") is not None,
    ])
    if defined_count != 1:
        return False
    if entry.get("serverName") is not None:
        if not isinstance(entry["serverName"], str):
            return False
        if not _MCP_SERVER_NAME_PATTERN.match(entry["serverName"]):
            return False
    if entry.get("serverCommand") is not None:
        if not isinstance(entry["serverCommand"], list) or len(entry["serverCommand"]) < 1:
            return False
    return True


# ---------------------------------------------------------------------------
# McpServerEntry union type
# ---------------------------------------------------------------------------

McpServerEntry = Union[AllowedMcpServerEntryDict, DeniedMcpServerEntryDict]


# ---------------------------------------------------------------------------
# Type guards for MCP server entries
# ---------------------------------------------------------------------------

def is_mcp_server_name_entry(
    entry: Dict[str, Any]
) -> bool:
    """
    Type guard for MCP server entry with serverName.
    Returns True if entry has a non-None serverName field.

    TypeScript equivalent:
        export function isMcpServerNameEntry(
            entry: AllowedMcpServerEntry | DeniedMcpServerEntry,
        ): entry is { serverName: string }
    """
    return "serverName" in entry and entry["serverName"] is not None


def is_mcp_server_command_entry(
    entry: Dict[str, Any]
) -> bool:
    """
    Type guard for MCP server entry with serverCommand.
    Returns True if entry has a non-None serverCommand field.

    TypeScript equivalent:
        export function isMcpServerCommandEntry(
            entry: AllowedMcpServerEntry | DeniedMcpServerEntry,
        ): entry is { serverCommand: string[] }
    """
    return "serverCommand" in entry and entry["serverCommand"] is not None


def is_mcp_server_url_entry(
    entry: Dict[str, Any]
) -> bool:
    """
    Type guard for MCP server entry with serverUrl.
    Returns True if entry has a non-None serverUrl field.

    TypeScript equivalent:
        export function isMcpServerUrlEntry(
            entry: AllowedMcpServerEntry | DeniedMcpServerEntry,
        ): entry is { serverUrl: string }
    """
    return "serverUrl" in entry and entry["serverUrl"] is not None


# ---------------------------------------------------------------------------
# SettingsJson — the top-level settings structure
# ---------------------------------------------------------------------------

class SettingsJson:
    """
    Top-level settings JSON structure.
    Python equivalent of z.infer<ReturnType<typeof SettingsSchema>>.

    All fields are optional to support backward compatibility.
    This class documents the schema; actual runtime values are plain dicts.
    """
    # JSON Schema reference
    schema: Optional[str]  # $schema field

    # Authentication helpers
    apiKeyHelper: Optional[str]
    awsCredentialExport: Optional[str]
    awsAuthRefresh: Optional[str]
    gcpAuthRefresh: Optional[str]

    # File suggestion configuration
    fileSuggestion: Optional[Dict[str, Any]]

    # Gitignore handling
    respectGitignore: Optional[bool]

    # Cleanup period for transcripts (days)
    cleanupPeriodDays: Optional[int]

    # Environment variables
    env: Optional[EnvironmentVariablesSchema]

    # Attribution for commits and PRs
    attribution: Optional[Dict[str, Any]]
    includeCoAuthoredBy: Optional[bool]
    includeGitInstructions: Optional[bool]

    # Permissions
    permissions: Optional[PermissionsDict]

    # Model configuration
    model: Optional[str]
    availableModels: Optional[List[str]]
    modelOverrides: Optional[Dict[str, str]]

    # MCP server configuration
    enableAllProjectMcpServers: Optional[bool]
    enabledMcpjsonServers: Optional[List[str]]
    disabledMcpjsonServers: Optional[List[str]]
    allowedMcpServers: Optional[List[AllowedMcpServerEntryDict]]
    deniedMcpServers: Optional[List[DeniedMcpServerEntryDict]]

    # Hooks configuration
    hooks: Optional[HooksSettings]
    disableAllHooks: Optional[bool]
    allowManagedHooksOnly: Optional[bool]

    # Worktree configuration
    worktree: Optional[Dict[str, Any]]

    # Shell
    defaultShell: Optional[Literal["bash", "powershell"]]

    # HTTP hook security
    allowedHttpHookUrls: Optional[List[str]]
    httpHookAllowedEnvVars: Optional[List[str]]

    # Permission management
    allowManagedPermissionRulesOnly: Optional[bool]
    allowManagedMcpServersOnly: Optional[bool]

    # Plugin-only customization
    strictPluginOnlyCustomization: Optional[
        Union[bool, List[Literal["skills", "agents", "hooks", "mcp"]]]
    ]

    # Status line
    statusLine: Optional[Dict[str, Any]]

    # Plugin configuration
    enabledPlugins: Optional[Dict[str, Any]]
    extraKnownMarketplaces: Optional[Dict[str, ExtraKnownMarketplaceDict]]
    strictKnownMarketplaces: Optional[List[Dict[str, Any]]]
    blockedMarketplaces: Optional[List[Dict[str, Any]]]
    pluginConfigs: Optional[Dict[str, Any]]

    # Login configuration
    forceLoginMethod: Optional[Literal["claudeai", "console"]]
    forceLoginOrgUUID: Optional[str]

    # Observability
    otelHeadersHelper: Optional[str]

    # Output configuration
    outputStyle: Optional[str]
    language: Optional[str]

    # Web fetch
    skipWebFetchPreflight: Optional[bool]

    # Sandbox
    sandbox: Optional[Dict[str, Any]]

    # Feedback survey
    feedbackSurveyRate: Optional[float]

    # Spinner configuration
    spinnerTipsEnabled: Optional[bool]
    spinnerVerbs: Optional[Dict[str, Any]]
    spinnerTipsOverride: Optional[Dict[str, Any]]

    # UI preferences
    syntaxHighlightingDisabled: Optional[bool]
    terminalTitleFromRename: Optional[bool]
    prefersReducedMotion: Optional[bool]

    # Thinking and effort
    alwaysThinkingEnabled: Optional[bool]
    effortLevel: Optional[str]

    # Advisor
    advisorModel: Optional[str]

    # Fast mode
    fastMode: Optional[bool]
    fastModePerSessionOptIn: Optional[bool]

    # Prompt suggestions
    promptSuggestionEnabled: Optional[bool]

    # Plan UI
    showClearContextOnPlanAccept: Optional[bool]

    # Agent
    agent: Optional[str]

    # Auto-memory
    autoMemoryEnabled: Optional[bool]
    autoMemoryDirectory: Optional[str]
    autoDreamEnabled: Optional[bool]

    # Thinking summaries
    showThinkingSummaries: Optional[bool]

    # Permission prompts
    skipDangerousModePermissionPrompt: Optional[bool]

    # Auto mode
    disableAutoMode: Optional[Literal["disable"]]

    # Auto mode classifier config
    autoMode: Optional[Dict[str, Any]]
    skipAutoPermissionPrompt: Optional[bool]
    useAutoModeDuringPlan: Optional[bool]

    # Classifier permissions
    classifierPermissionsEnabled: Optional[bool]

    # Sleep durations (proactive/kairos)
    minSleepDurationMs: Optional[int]
    maxSleepDurationMs: Optional[int]

    # Voice mode
    voiceEnabled: Optional[bool]

    # Assistant/KAIROS
    assistant: Optional[bool]
    assistantName: Optional[str]

    # Channels
    channelsEnabled: Optional[bool]
    allowedChannelPlugins: Optional[List[Dict[str, Any]]]

    # View defaults
    defaultView: Optional[Literal["chat", "transcript"]]

    # Announcements
    companyAnnouncements: Optional[List[str]]

    # Remote sessions
    remote: Optional[Dict[str, Any]]

    # Auto-updates
    autoUpdatesChannel: Optional[Literal["latest", "stable"]]

    # Deep link registration
    disableDeepLinkRegistration: Optional[Literal["disable"]]

    # Minimum version
    minimumVersion: Optional[str]

    # Plans directory
    plansDirectory: Optional[str]

    # SSH configurations
    sshConfigs: Optional[List[Dict[str, Any]]]

    # CLAUDE.md excludes
    claudeMdExcludes: Optional[List[str]]

    # Plugin trust message
    pluginTrustMessage: Optional[str]

    # XAA IdP connection
    xaaIdp: Optional[Dict[str, Any]]


# ---------------------------------------------------------------------------
# PluginHookMatcher — internal type, not user-facing
# ---------------------------------------------------------------------------

class PluginHookMatcher:
    """Internal type for plugin hooks — includes plugin context for execution."""
    matcher: Optional[str]
    hooks: List[HookCommand]
    pluginRoot: str
    pluginName: str
    pluginId: str  # format: "pluginName@marketplaceName"


# ---------------------------------------------------------------------------
# SkillHookMatcher — internal type, not user-facing
# ---------------------------------------------------------------------------

class SkillHookMatcher:
    """Internal type for skill hooks — includes skill context for execution."""
    matcher: Optional[str]
    hooks: List[HookCommand]
    skillRoot: str
    skillName: str


# ---------------------------------------------------------------------------
# UserConfigValues / PluginConfig
# ---------------------------------------------------------------------------

# User configuration values for MCP servers
UserConfigValues = Dict[str, Union[str, int, bool, List[str]]]

# Plugin configuration stored in settings.json
PluginConfig = Dict[str, Any]  # has optional 'mcpServers' key


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_environment_variables(env: Any) -> bool:
    """Validate that env is a dict with string keys and string-coercible values."""
    if not isinstance(env, dict):
        return False
    for k, v in env.items():
        if not isinstance(k, str):
            return False
        # Values are coerced to strings, so any scalar is valid
        if not isinstance(v, (str, int, float, bool)):
            return False
    return True


def coerce_env_var_value(value: Any) -> str:
    """Coerce an environment variable value to a string (mirrors z.coerce.string())."""
    return str(value)


def preprocess_strict_plugin_only_customization(value: Any) -> Any:
    """
    Preprocess strictPluginOnlyCustomization to forward-compat:
    drop unknown surface names from arrays.
    """
    if isinstance(value, list):
        return [x for x in value if x in CUSTOMIZATION_SURFACES]
    return value


def validate_strict_plugin_only_customization(value: Any) -> bool:
    """Validate strictPluginOnlyCustomization field."""
    processed = preprocess_strict_plugin_only_customization(value)
    if isinstance(processed, bool):
        return True
    if isinstance(processed, list):
        return all(x in CUSTOMIZATION_SURFACES for x in processed)
    return False
