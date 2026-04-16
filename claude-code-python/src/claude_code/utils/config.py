"""
配置读写工具 — 完整移植自 utils/config.ts

全局配置: ~/.claude/claude.json
项目配置: 嵌套在 globalConfig.projects[<project_path>] 中
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore

# ---------------------------------------------------------------------------
# Type definitions (TypedDict equivalents of TS interfaces)
# ---------------------------------------------------------------------------

class McpServerConfig(TypedDict, total=False):
    """Minimal stub for MCP server config."""
    command: str
    args: List[str]
    env: Dict[str, str]
    url: str
    headers: Dict[str, str]


class ImageDimensions(TypedDict, total=False):
    width: int
    height: int
    originalWidth: int
    originalHeight: int


class PastedContent(TypedDict, total=False):
    id: int                  # Sequential numeric ID
    type: str                # 'text' | 'image'
    content: str
    mediaType: str           # e.g. 'image/png', 'image/jpeg'
    filename: str            # Display name for images
    dimensions: ImageDimensions
    sourcePath: str          # Original file path for dragged images


class HistoryEntry(TypedDict, total=False):
    display: str
    pastedContents: Dict[int, PastedContent]


class AccountInfo(TypedDict, total=False):
    accountUuid: str
    emailAddress: str
    organizationUuid: str
    organizationName: Optional[str]
    organizationRole: Optional[str]
    workspaceRole: Optional[str]
    displayName: str
    hasExtraUsageEnabled: bool
    billingType: Optional[str]
    accountCreatedAt: str
    subscriptionCreatedAt: str


class _WorktreeSession(TypedDict, total=False):
    originalCwd: str
    worktreePath: str
    worktreeName: str
    originalBranch: str
    sessionId: str
    hookBased: bool


class ProjectConfig(TypedDict, total=False):
    allowedTools: List[str]
    mcpContextUris: List[str]
    mcpServers: Dict[str, McpServerConfig]
    lastAPIDuration: float
    lastAPIDurationWithoutRetries: float
    lastToolDuration: float
    lastCost: float
    lastDuration: float
    lastLinesAdded: int
    lastLinesRemoved: int
    lastTotalInputTokens: int
    lastTotalOutputTokens: int
    lastTotalCacheCreationInputTokens: int
    lastTotalCacheReadInputTokens: int
    lastTotalWebSearchRequests: int
    lastFpsAverage: float
    lastFpsLow1Pct: float
    lastSessionId: str
    lastModelUsage: Dict[str, Any]
    lastSessionMetrics: Dict[str, float]
    exampleFiles: List[str]
    exampleFilesGeneratedAt: float
    hasTrustDialogAccepted: bool
    hasCompletedProjectOnboarding: bool
    projectOnboardingSeenCount: int
    hasClaudeMdExternalIncludesApproved: bool
    hasClaudeMdExternalIncludesWarningShown: bool
    enabledMcpjsonServers: List[str]
    disabledMcpjsonServers: List[str]
    enableAllProjectMcpServers: bool
    disabledMcpServers: List[str]
    enabledMcpServers: List[str]
    activeWorktreeSession: _WorktreeSession
    remoteControlSpawnMode: str   # 'same-dir' | 'worktree'


class _CustomApiKeyResponses(TypedDict, total=False):
    approved: List[str]
    rejected: List[str]


class _S1mAccessEntry(TypedDict, total=False):
    hasAccess: bool
    hasAccessNotAsDefault: bool
    timestamp: int


class GlobalConfig(TypedDict, total=False):
    apiKeyHelper: str
    projects: Dict[str, ProjectConfig]
    numStartups: int
    installMethod: str       # 'local' | 'native' | 'global' | 'unknown'
    autoUpdates: bool
    autoUpdatesProtectedForNative: bool
    doctorShownAtSession: int
    userID: str
    theme: str               # ThemeSetting
    hasCompletedOnboarding: bool
    lastOnboardingVersion: str
    lastReleaseNotesSeen: str
    changelogLastFetched: int
    cachedChangelog: str
    mcpServers: Dict[str, McpServerConfig]
    claudeAiMcpEverConnected: List[str]
    preferredNotifChannel: str  # NotificationChannel
    customNotifyCommand: str
    verbose: bool
    customApiKeyResponses: _CustomApiKeyResponses
    primaryApiKey: str
    hasAcknowledgedCostThreshold: bool
    hasSeenUndercoverAutoNotice: bool
    hasSeenUltraplanTerms: bool
    hasResetAutoModeOptInForDefaultOffer: bool
    oauthAccount: AccountInfo
    iterm2KeyBindingInstalled: bool
    editorMode: str          # EditorMode
    bypassPermissionsModeAccepted: bool
    hasUsedBackslashReturn: bool
    autoCompactEnabled: bool
    showTurnDuration: bool
    env: Dict[str, str]
    hasSeenTasksHint: bool
    hasUsedStash: bool
    hasUsedBackgroundTask: bool
    queuedCommandUpHintCount: int
    diffTool: str            # 'terminal' | 'auto'
    iterm2SetupInProgress: bool
    iterm2BackupPath: str
    appleTerminalBackupPath: str
    appleTerminalSetupInProgress: bool
    shiftEnterKeyBindingInstalled: bool
    optionAsMetaKeyInstalled: bool
    autoConnectIde: bool
    autoInstallIdeExtension: bool
    hasIdeOnboardingBeenShown: Dict[str, bool]
    ideHintShownCount: int
    hasIdeAutoConnectDialogBeenShown: bool
    tipsHistory: Dict[str, int]
    companion: Any
    companionMuted: bool
    feedbackSurveyState: Dict[str, Any]
    transcriptShareDismissed: bool
    memoryUsageCount: int
    hasShownS1MWelcomeV2: Dict[str, bool]
    s1mAccessCache: Dict[str, _S1mAccessEntry]
    s1mNonSubscriberAccessCache: Dict[str, _S1mAccessEntry]
    passesEligibilityCache: Dict[str, Any]
    groveConfigCache: Dict[str, Any]
    passesUpsellSeenCount: int
    hasVisitedPasses: bool
    passesLastSeenRemaining: int
    overageCreditGrantCache: Dict[str, Any]
    overageCreditUpsellSeenCount: int
    hasVisitedExtraUsage: bool
    voiceNoticeSeenCount: int
    voiceLangHintShownCount: int
    voiceLangHintLastLanguage: str
    voiceFooterHintSeenCount: int
    opus1mMergeNoticeSeenCount: int
    experimentNoticesSeenCount: Dict[str, int]
    hasShownOpusPlanWelcome: Dict[str, bool]
    promptQueueUseCount: int
    btwUseCount: int
    lastPlanModeUse: int
    subscriptionNoticeCount: int
    hasAvailableSubscription: bool
    subscriptionUpsellShownCount: int
    recommendedSubscription: str
    todoFeatureEnabled: bool
    showExpandedTodos: bool
    showSpinnerTree: bool
    firstStartTime: str
    messageIdleNotifThresholdMs: int
    githubActionSetupCount: int
    slackAppInstallCount: int
    fileCheckpointingEnabled: bool
    terminalProgressBarEnabled: bool
    showStatusInTerminalTab: bool
    taskCompleteNotifEnabled: bool
    inputNeededNotifEnabled: bool
    agentPushNotifEnabled: bool
    claudeCodeFirstTokenDate: str
    modelSwitchCalloutDismissed: bool
    modelSwitchCalloutLastShown: int
    modelSwitchCalloutVersion: str
    effortCalloutDismissed: bool
    effortCalloutV2Dismissed: bool
    remoteDialogSeen: bool
    bridgeOauthDeadExpiresAt: int
    bridgeOauthDeadFailCount: int
    desktopUpsellSeenCount: int
    desktopUpsellDismissed: bool
    idleReturnDismissed: bool
    opusProMigrationComplete: bool
    opusProMigrationTimestamp: int
    sonnet1m45MigrationComplete: bool
    legacyOpusMigrationTimestamp: int
    sonnet45To46MigrationTimestamp: int
    cachedStatsigGates: Dict[str, bool]
    cachedDynamicConfigs: Dict[str, Any]
    cachedGrowthBookFeatures: Dict[str, Any]
    growthBookOverrides: Dict[str, Any]
    lastShownEmergencyTip: str
    respectGitignore: bool
    copyFullResponse: bool
    copyOnSelect: bool
    githubRepoPaths: Dict[str, List[str]]
    deepLinkTerminal: str
    iterm2It2SetupComplete: bool
    preferTmuxOverIterm2: bool
    skillUsage: Dict[str, Any]
    officialMarketplaceAutoInstallAttempted: bool
    officialMarketplaceAutoInstalled: bool
    officialMarketplaceAutoInstallFailReason: str
    officialMarketplaceAutoInstallRetryCount: int
    officialMarketplaceAutoInstallLastAttemptTime: int
    officialMarketplaceAutoInstallNextRetryTime: int
    hasCompletedClaudeInChromeOnboarding: bool
    claudeInChromeDefaultEnabled: bool
    cachedChromeExtensionInstalled: bool
    chromeExtension: Dict[str, Any]
    lspRecommendationDisabled: bool
    lspRecommendationNeverPlugins: List[str]
    lspRecommendationIgnoredCount: int
    claudeCodeHints: Dict[str, Any]
    permissionExplainerEnabled: bool
    teammateMode: str        # 'auto' | 'tmux' | 'in-process'
    teammateDefaultModel: Optional[str]
    prStatusFooterEnabled: bool
    tungstenPanelVisible: bool
    penguinModeOrgEnabled: bool
    startupPrefetchedAt: int
    remoteControlAtStartup: bool
    cachedExtraUsageDisabledReason: Optional[str]
    autoPermissionsNotificationCount: int
    speculationEnabled: bool
    clientDataCache: Optional[Dict[str, Any]]
    additionalModelOptionsCache: List[Any]
    metricsStatusCache: Dict[str, Any]
    migrationVersion: int


# ---------------------------------------------------------------------------
# Default configs
# ---------------------------------------------------------------------------

def _create_default_global_config() -> GlobalConfig:
    """Factory for a fresh default GlobalConfig (mirrors createDefaultGlobalConfig in TS)."""
    return {
        "numStartups": 0,
        "installMethod": None,
        "autoUpdates": None,
        "theme": "dark",
        "preferredNotifChannel": "auto",
        "verbose": False,
        "editorMode": "normal",
        "autoCompactEnabled": True,
        "showTurnDuration": True,
        "hasSeenTasksHint": False,
        "hasUsedStash": False,
        "hasUsedBackgroundTask": False,
        "queuedCommandUpHintCount": 0,
        "diffTool": "auto",
        "customApiKeyResponses": {
            "approved": [],
            "rejected": [],
        },
        "env": {},
        "tipsHistory": {},
        "memoryUsageCount": 0,
        "promptQueueUseCount": 0,
        "btwUseCount": 0,
        "todoFeatureEnabled": True,
        "showExpandedTodos": False,
        "messageIdleNotifThresholdMs": 60000,
        "autoConnectIde": False,
        "autoInstallIdeExtension": True,
        "fileCheckpointingEnabled": True,
        "terminalProgressBarEnabled": True,
        "cachedStatsigGates": {},
        "cachedDynamicConfigs": {},
        "cachedGrowthBookFeatures": {},
        "respectGitignore": True,
        "copyFullResponse": False,
    }


DEFAULT_GLOBAL_CONFIG: GlobalConfig = _create_default_global_config()

_DEFAULT_PROJECT_CONFIG: ProjectConfig = {
    "allowedTools": [],
    "mcpContextUris": [],
    "mcpServers": {},
    "enabledMcpjsonServers": [],
    "disabledMcpjsonServers": [],
    "hasTrustDialogAccepted": False,
    "projectOnboardingSeenCount": 0,
    "hasClaudeMdExternalIncludesApproved": False,
    "hasClaudeMdExternalIncludesWarningShown": False,
}

# ---------------------------------------------------------------------------
# Config key lists
# ---------------------------------------------------------------------------

GLOBAL_CONFIG_KEYS: Tuple[str, ...] = (
    "apiKeyHelper",
    "installMethod",
    "autoUpdates",
    "autoUpdatesProtectedForNative",
    "theme",
    "verbose",
    "preferredNotifChannel",
    "shiftEnterKeyBindingInstalled",
    "editorMode",
    "hasUsedBackslashReturn",
    "autoCompactEnabled",
    "showTurnDuration",
    "diffTool",
    "env",
    "tipsHistory",
    "todoFeatureEnabled",
    "showExpandedTodos",
    "messageIdleNotifThresholdMs",
    "autoConnectIde",
    "autoInstallIdeExtension",
    "fileCheckpointingEnabled",
    "terminalProgressBarEnabled",
    "showStatusInTerminalTab",
    "taskCompleteNotifEnabled",
    "inputNeededNotifEnabled",
    "agentPushNotifEnabled",
    "respectGitignore",
    "claudeInChromeDefaultEnabled",
    "hasCompletedClaudeInChromeOnboarding",
    "lspRecommendationDisabled",
    "lspRecommendationNeverPlugins",
    "lspRecommendationIgnoredCount",
    "copyFullResponse",
    "copyOnSelect",
    "permissionExplainerEnabled",
    "prStatusFooterEnabled",
    "remoteControlAtStartup",
    "remoteDialogSeen",
)

PROJECT_CONFIG_KEYS: Tuple[str, ...] = (
    "allowedTools",
    "hasTrustDialogAccepted",
    "hasCompletedProjectOnboarding",
)

# ---------------------------------------------------------------------------
# Config file path helpers
# ---------------------------------------------------------------------------

def _get_global_claude_file() -> Path:
    """Returns the path to the global claude config file (~/.claude/claude.json)."""
    claude_home = Path.home() / ".claude"
    return claude_home / "claude.json"


def _get_claude_config_home_dir() -> Path:
    return Path.home() / ".claude"

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

_global_config_cache: Optional[GlobalConfig] = None


def _invalidate_cache() -> None:
    global _global_config_cache
    _global_config_cache = None


# ---------------------------------------------------------------------------
# Low-level read/write helpers
# ---------------------------------------------------------------------------

def _strip_bom(text: str) -> str:
    """Strip UTF-8 BOM that PowerShell 5.x may add."""
    return text.lstrip("\ufeff")


def _read_config_file(path: Path) -> Optional[Dict[str, Any]]:
    """Read and JSON-parse a config file. Returns None if file not found."""
    try:
        content = path.read_text(encoding="utf-8")
        return json.loads(_strip_bom(content))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        return None


def _write_config_file(path: Path, data: Dict[str, Any]) -> None:
    """Write config dict to path with mode 0o600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(path)
    except Exception:
        # Fallback: direct write
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        path.chmod(0o600)


def _migrate_config_fields(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate old autoUpdaterStatus to installMethod + autoUpdates.
    Mirrors migrateConfigFields() in TS.
    """
    if config.get("installMethod") is not None:
        return config

    legacy_status = config.get("autoUpdaterStatus")
    install_method = "unknown"
    auto_updates = config.get("autoUpdates", True)

    if legacy_status == "migrated":
        install_method = "local"
    elif legacy_status == "installed":
        install_method = "native"
    elif legacy_status == "disabled":
        auto_updates = False
    elif legacy_status in ("enabled", "no_permissions", "not_configured"):
        install_method = "global"

    return {**config, "installMethod": install_method, "autoUpdates": auto_updates}


# ---------------------------------------------------------------------------
# get_global_config / save_global_config
# ---------------------------------------------------------------------------

def get_global_config() -> GlobalConfig:
    """
    Read the global config from ~/.claude/claude.json.
    Merges with defaults and caches the result.
    Mirrors getGlobalConfig() in TS.
    """
    global _global_config_cache

    if _global_config_cache is not None:
        return _global_config_cache

    config_file = _get_global_claude_file()
    raw = _read_config_file(config_file)

    defaults = _create_default_global_config()
    if raw is None:
        _global_config_cache = defaults
    else:
        merged: Dict[str, Any] = {**defaults, **raw}
        migrated = _migrate_config_fields(merged)
        _global_config_cache = migrated  # type: ignore[assignment]

    return _global_config_cache  # type: ignore[return-value]


def save_global_config(updater: Any = None, **kwargs: Any) -> None:
    """
    Persist the global config back to ~/.claude/claude.json.

    Two calling styles:
      1. save_global_config(lambda current: {**current, "key": value})
      2. save_global_config(key=value, ...)  (convenience)

    Mirrors saveGlobalConfig() in TS (simplified — no lockfile for Python port).
    """
    global _global_config_cache

    current = get_global_config()

    if callable(updater):
        new_config = updater(current)
    elif updater is None and kwargs:
        new_config = {**current, **kwargs}
    elif isinstance(updater, dict):
        new_config = {**current, **updater}
    else:
        raise TypeError("save_global_config requires a callable updater or keyword args")

    if new_config is current:
        return  # no-op

    # Write to disk (only non-default values)
    _write_config_file(_get_global_claude_file(), new_config)
    _global_config_cache = new_config  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Trust helpers
# ---------------------------------------------------------------------------

def _normalize_path_for_config_key(path: str) -> str:
    """Normalize path to forward slashes for use as a JSON key."""
    return str(Path(path).resolve()).replace("\\", "/")


_trust_accepted: bool = False


def reset_trust_dialog_accepted_cache_for_testing() -> None:
    global _trust_accepted
    _trust_accepted = False


def check_has_trust_dialog_accepted() -> bool:
    """
    Returns True if the trust dialog has been accepted for the current CWD
    (or any of its parents). Mirrors checkHasTrustDialogAccepted() in TS.
    """
    global _trust_accepted
    if _trust_accepted:
        return True
    _trust_accepted = _compute_trust_dialog_accepted()
    return _trust_accepted


def _compute_trust_dialog_accepted() -> bool:
    config = get_global_config()
    cwd = _normalize_path_for_config_key(os.getcwd())
    current_path = cwd

    while True:
        path_config = (config.get("projects") or {}).get(current_path)
        if path_config and path_config.get("hasTrustDialogAccepted"):
            return True
        parent_path = _normalize_path_for_config_key(
            str(Path(current_path).parent)
        )
        if parent_path == current_path:
            break
        current_path = parent_path

    return False


def is_path_trusted(dir_path: str) -> bool:
    """
    Check trust for an arbitrary directory (not necessarily cwd).
    Walks up from `dir_path`, returning True if any ancestor has trust persisted.
    Mirrors isPathTrusted() in TS.
    """
    config = get_global_config()
    current_path = _normalize_path_for_config_key(str(Path(dir_path).resolve()))

    while True:
        projects = config.get("projects") or {}
        if projects.get(current_path, {}).get("hasTrustDialogAccepted"):
            return True
        parent_path = _normalize_path_for_config_key(
            str(Path(current_path).parent)
        )
        if parent_path == current_path:
            return False
        current_path = parent_path


# ---------------------------------------------------------------------------
# Type guard helpers
# ---------------------------------------------------------------------------

def is_global_config_key(key: str) -> bool:
    """Type guard: is `key` a valid GlobalConfig key? Mirrors isGlobalConfigKey()."""
    return key in GLOBAL_CONFIG_KEYS


def is_project_config_key(key: str) -> bool:
    """Type guard: is `key` a valid ProjectConfig key? Mirrors isProjectConfigKey()."""
    return key in PROJECT_CONFIG_KEYS


# ---------------------------------------------------------------------------
# Remote control
# ---------------------------------------------------------------------------

def get_remote_control_at_startup() -> bool:
    """
    Returns the effective remoteControlAtStartup value.
    Precedence: explicit config > False.
    Mirrors getRemoteControlAtStartup() in TS (CCR auto-connect omitted).
    """
    explicit = get_global_config().get("remoteControlAtStartup")
    if explicit is not None:
        return bool(explicit)
    return False


# ---------------------------------------------------------------------------
# Custom API key status
# ---------------------------------------------------------------------------

def get_custom_api_key_status(
    truncated_api_key: str,
) -> str:  # 'approved' | 'rejected' | 'new'
    """
    Returns 'approved', 'rejected', or 'new' based on the stored custom API key
    responses in the global config. Mirrors getCustomApiKeyStatus() in TS.
    """
    config = get_global_config()
    responses = config.get("customApiKeyResponses") or {}
    if truncated_api_key in (responses.get("approved") or []):
        return "approved"
    if truncated_api_key in (responses.get("rejected") or []):
        return "rejected"
    return "new"


# ---------------------------------------------------------------------------
# Project config helpers (simplified — project path = cwd)
# ---------------------------------------------------------------------------

def _get_project_path_for_config() -> str:
    """
    Returns the canonical project path for config lookup.
    Tries to find git root; falls back to cwd.
    """
    cwd = os.getcwd()
    # Walk up looking for .git
    candidate = Path(cwd)
    while True:
        if (candidate / ".git").exists():
            return _normalize_path_for_config_key(str(candidate))
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return _normalize_path_for_config_key(cwd)


def get_current_project_config() -> ProjectConfig:
    """Returns the ProjectConfig for the current working directory."""
    path = _get_project_path_for_config()
    config = get_global_config()
    projects = config.get("projects") or {}
    return projects.get(path, dict(_DEFAULT_PROJECT_CONFIG))  # type: ignore[return-value]


def save_current_project_config(
    updater: Any,
) -> None:
    """
    Save an updated ProjectConfig for the current working directory.
    updater is called with the current ProjectConfig and should return the new one.
    """
    path = _get_project_path_for_config()
    current_global = get_global_config()
    projects = dict(current_global.get("projects") or {})
    current_project = projects.get(path, dict(_DEFAULT_PROJECT_CONFIG))

    if callable(updater):
        new_project = updater(current_project)
    elif isinstance(updater, dict):
        new_project = {**current_project, **updater}
    else:
        raise TypeError("updater must be callable or dict")

    if new_project is current_project:
        return

    projects[path] = new_project
    save_global_config(lambda c: {**c, "projects": projects})


# ---------------------------------------------------------------------------
# Legacy compatibility — keep old API working
# ---------------------------------------------------------------------------

def get_config_value(key: str, default: Any = None) -> Any:
    """Legacy: read a top-level config value with env-var override."""
    env_key = "CLAUDE_" + key.upper().replace(".", "_")
    if env_key in os.environ:
        return os.environ[env_key]
    config = get_global_config()
    return config.get(key, default)


def set_config_value(key: str, value: Any) -> None:
    """Legacy: set a top-level config value."""
    save_global_config(lambda c: {**c, key: value})


def delete_config_value(key: str) -> bool:
    """Legacy: delete a top-level config value."""
    config = get_global_config()
    if key not in config:
        return False
    new_config = {k: v for k, v in config.items() if k != key}
    save_global_config(lambda _c: new_config)
    return True


def get_all_config() -> Dict[str, Any]:
    """Legacy: return the full global config dict."""
    return dict(get_global_config())
