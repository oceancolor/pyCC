"""
permission_setup.py — Permission mode setup and transition helpers.

Ported from: utils/permissions/permissionSetup.ts (1532 lines)
"""
from __future__ import annotations

import logging
import os
import re
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    TypedDict,
    Union,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy module helpers
# ---------------------------------------------------------------------------

def _try_import_permission_rule_parser():
    try:
        from claude_code.utils.permissions import permission_rule_parser  # type: ignore[import]
        return permission_rule_parser
    except ImportError:
        return None


def _try_import_permission_update():
    try:
        from claude_code.utils.permissions import permission_update  # type: ignore[import]
        return permission_update
    except ImportError:
        return None


def _try_import_dangerous_patterns():
    try:
        from claude_code.utils.permissions import dangerous_patterns  # type: ignore[import]
        return dangerous_patterns
    except ImportError:
        return None


def _try_import_permissions_loader():
    try:
        from claude_code.utils.permissions import permissions_loader  # type: ignore[import]
        return permissions_loader
    except ImportError:
        return None


def _try_import_auto_mode_state():
    try:
        from claude_code.utils.permissions import auto_mode_state  # type: ignore[import]
        return auto_mode_state
    except ImportError:
        return None


def _try_import_permissions():
    try:
        from claude_code.utils.permissions import permissions  # type: ignore[import]
        return permissions
    except ImportError:
        return None


def _try_import_settings():
    try:
        from claude_code.utils import settings  # type: ignore[import]
        return settings
    except ImportError:
        return None


def _try_import_bootstrap_state():
    try:
        from claude_code.bootstrap import state  # type: ignore[import]
        return state
    except ImportError:
        return None


def _try_import_growthbook():
    try:
        from claude_code.services.analytics import growthbook  # type: ignore[import]
        return growthbook
    except ImportError:
        return None


def _try_import_add_dir_validation():
    try:
        from claude_code.commands.add_dir import validation  # type: ignore[import]
        return validation
    except ImportError:
        return None


def _try_import_tools_module():
    try:
        import claude_code.tools as tools_module  # type: ignore[import]
        return tools_module
    except ImportError:
        return None


def _try_import_betas():
    try:
        from claude_code.utils import betas  # type: ignore[import]
        return betas
    except ImportError:
        return None


def _try_import_graceful_shutdown():
    try:
        from claude_code.utils import graceful_shutdown  # type: ignore[import]
        return graceful_shutdown
    except ImportError:
        return None


def _try_import_fs_operations():
    try:
        from claude_code.utils import fs_operations  # type: ignore[import]
        return fs_operations
    except ImportError:
        return None


def _try_import_model():
    try:
        from claude_code.utils.model import model as model_mod  # type: ignore[import]
        return model_mod
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

class PermissionRuleValueFull(TypedDict, total=False):
    toolName: str
    ruleContent: str


PermissionBehavior = Literal["allow", "deny", "ask"]
PermissionRuleSource = str


class PermissionRule(TypedDict):
    source: PermissionRuleSource
    ruleBehavior: PermissionBehavior
    ruleValue: PermissionRuleValueFull


class ToolPermissionRulesBySource(TypedDict, total=False):
    policySettings: List[str]
    flagSettings: List[str]
    userSettings: List[str]
    projectSettings: List[str]
    localSettings: List[str]
    cliArg: List[str]
    command: List[str]
    session: List[str]


class ToolPermissionContext(TypedDict, total=False):
    mode: str
    alwaysAllowRules: ToolPermissionRulesBySource
    alwaysDenyRules: ToolPermissionRulesBySource
    alwaysAskRules: ToolPermissionRulesBySource
    additionalWorkingDirectories: Dict[str, Any]
    isBypassPermissionsModeAvailable: bool
    isAutoModeAvailable: bool
    shouldAvoidPermissionPrompts: bool
    prePlanMode: Optional[str]
    strippedDangerousRules: Optional[ToolPermissionRulesBySource]


class DangerousPermissionInfo(TypedDict):
    """Structured info about a dangerous permission rule."""
    ruleValue: PermissionRuleValueFull
    source: PermissionRuleSource
    ruleDisplay: str    # e.g. "Bash(*)" or "Bash(python:*)"
    sourceDisplay: str  # e.g. a file path or "--allowed-tools"


AutoModeEnabledState = Literal["enabled", "disabled", "opt-in"]
AUTO_MODE_ENABLED_DEFAULT: AutoModeEnabledState = "disabled"


class AutoModeGateCheckResult(TypedDict, total=False):
    """Result of verifyAutoModeGateAccess."""
    # Transform function applied inside setAppState against the current context
    updateContext: Callable[[ToolPermissionContext], ToolPermissionContext]
    notification: Optional[str]


AutoModeUnavailableReason = Literal["settings", "circuit-breaker", "model"]

SETTING_SOURCES: Tuple[str, ...] = (
    "policySettings",
    "flagSettings",
    "userSettings",
    "projectSettings",
    "localSettings",
)

# ---------------------------------------------------------------------------
# Tool name constants (with fallbacks)
# ---------------------------------------------------------------------------

def _get_bash_tool_name() -> str:
    try:
        from claude_code.tools.bash_tool.tool_name import BASH_TOOL_NAME  # type: ignore[import]
        return BASH_TOOL_NAME
    except ImportError:
        return "Bash"


def _get_powershell_tool_name() -> str:
    try:
        from claude_code.tools.powershell_tool.tool_name import POWERSHELL_TOOL_NAME  # type: ignore[import]
        return POWERSHELL_TOOL_NAME
    except ImportError:
        return "PowerShell"


def _get_agent_tool_name() -> str:
    try:
        from claude_code.tools.agent_tool.constants import AGENT_TOOL_NAME  # type: ignore[import]
        return AGENT_TOOL_NAME
    except ImportError:
        return "Agent"


# ---------------------------------------------------------------------------
# Rule parser helpers
# ---------------------------------------------------------------------------

def _permission_rule_value_from_string(rule_string: str) -> PermissionRuleValueFull:
    """Parse 'Bash(prefix:*)' → PermissionRuleValue."""
    mod = _try_import_permission_rule_parser()
    if mod and hasattr(mod, "permission_rule_value_from_string"):
        return mod.permission_rule_value_from_string(rule_string)  # type: ignore[no-any-return]
    # Fallback
    if "(" in rule_string and rule_string.endswith(")"):
        idx = rule_string.index("(")
        tool_name = rule_string[:idx]
        rule_content = rule_string[idx + 1: -1]
        if rule_content and rule_content != "*":
            return {"toolName": tool_name, "ruleContent": rule_content}
        return {"toolName": tool_name}
    return {"toolName": rule_string}


def _permission_rule_value_to_string(rule_value: PermissionRuleValueFull) -> str:
    """Serialize PermissionRuleValue → string."""
    mod = _try_import_permission_rule_parser()
    if mod and hasattr(mod, "permission_rule_value_to_string"):
        return mod.permission_rule_value_to_string(rule_value)  # type: ignore[no-any-return]
    tool_name = rule_value.get("toolName", "")
    rule_content = rule_value.get("ruleContent")
    if rule_content is not None:
        return f"{tool_name}({rule_content})"
    return tool_name


def _normalize_legacy_tool_name(tool_name: str) -> str:
    """Normalize legacy tool names (e.g. 'Task' → 'Agent')."""
    mod = _try_import_permission_rule_parser()
    if mod and hasattr(mod, "normalize_legacy_tool_name"):
        return mod.normalize_legacy_tool_name(tool_name)  # type: ignore[no-any-return]
    # Fallback: known renames
    if tool_name == "Task":
        return "Agent"
    return tool_name


# ---------------------------------------------------------------------------
# Source display name
# ---------------------------------------------------------------------------

def _format_permission_source(source: PermissionRuleSource) -> str:
    """
    Format a permission rule source for display.
    For settings sources, try to resolve to a relative file path.
    """
    if source in SETTING_SOURCES:
        try:
            from claude_code.utils.settings.settings import get_settings_file_path_for_source  # type: ignore[import]
            from claude_code.utils.cwd import get_cwd  # type: ignore[import]
            file_path = get_settings_file_path_for_source(source)
            if file_path:
                cwd = get_cwd()
                rel = os.path.relpath(file_path, cwd)
                return rel if len(rel) < len(file_path) else file_path
        except ImportError:
            pass
    return source


# ---------------------------------------------------------------------------
# Dangerous patterns helpers
# ---------------------------------------------------------------------------

def _get_dangerous_bash_patterns() -> List[str]:
    """Return the list of dangerous bash command patterns."""
    mod = _try_import_dangerous_patterns()
    if mod and hasattr(mod, "DANGEROUS_BASH_PATTERNS"):
        return list(mod.DANGEROUS_BASH_PATTERNS)
    # Fallback list (common script interpreters)
    return [
        "python", "python3", "python2",
        "node", "nodejs",
        "ruby", "perl", "php", "lua",
        "sh", "bash", "zsh", "dash", "ksh",
        "curl", "wget",
    ]


def _get_cross_platform_code_exec() -> List[str]:
    """Return cross-platform code execution patterns."""
    mod = _try_import_dangerous_patterns()
    if mod and hasattr(mod, "CROSS_PLATFORM_CODE_EXEC"):
        return list(mod.CROSS_PLATFORM_CODE_EXEC)
    return [
        "python", "python3", "node", "nodejs",
        "ruby", "perl", "php", "lua",
        "sh", "bash",
    ]


# ---------------------------------------------------------------------------
# isDangerousBashPermission
# ---------------------------------------------------------------------------

def is_dangerous_bash_permission(
    tool_name: str,
    rule_content: Optional[str],
) -> bool:
    """
    Checks if a Bash permission rule is dangerous for auto mode.
    A rule is dangerous if it would auto-allow commands that execute arbitrary code,
    bypassing the classifier's safety evaluation.

    Dangerous patterns:
    1. Tool-level allow (Bash with no ruleContent) - allows ALL commands
    2. Prefix rules for script interpreters (python:*, node:*, etc.)
    3. Wildcard rules matching interpreters (python*, node*, etc.)
    """
    BASH_TOOL_NAME = _get_bash_tool_name()
    if tool_name != BASH_TOOL_NAME:
        return False

    # Tool-level allow (no content, or empty, or '*')
    if rule_content is None or rule_content == "":
        return True

    content = rule_content.strip().lower()

    # Standalone wildcard
    if content == "*":
        return True

    dangerous_patterns = _get_dangerous_bash_patterns()
    for pattern in dangerous_patterns:
        lower_pattern = pattern.lower()

        # Exact match
        if content == lower_pattern:
            return True
        # Prefix syntax: "python:*"
        if content == f"{lower_pattern}:*":
            return True
        # Wildcard at end: "python*"
        if content == f"{lower_pattern}*":
            return True
        # Wildcard with space: "python *"
        if content == f"{lower_pattern} *":
            return True
        # Pattern like "python -*"
        if content.startswith(f"{lower_pattern} -") and content.endswith("*"):
            return True

    return False


# ---------------------------------------------------------------------------
# isDangerousPowerShellPermission
# ---------------------------------------------------------------------------

def is_dangerous_powershell_permission(
    tool_name: str,
    rule_content: Optional[str],
) -> bool:
    """
    Checks if a PowerShell permission rule is dangerous for auto mode.
    A rule is dangerous if it would auto-allow commands that execute arbitrary
    code (nested shells, Invoke-Expression, Start-Process, etc.), bypassing the
    classifier's safety evaluation.

    PowerShell is case-insensitive, so rule content is lowercased before matching.
    """
    POWERSHELL_TOOL_NAME = _get_powershell_tool_name()
    if tool_name != POWERSHELL_TOOL_NAME:
        return False

    # Tool-level allow
    if rule_content is None or rule_content == "":
        return True

    content = rule_content.strip().lower()

    if content == "*":
        return True

    cross_platform = _get_cross_platform_code_exec()
    patterns: List[str] = [
        *[p.lower() for p in cross_platform],
        # Nested PS + shells launchable from PS
        "pwsh",
        "powershell",
        "cmd",
        "wsl",
        # String/scriptblock evaluators
        "iex",
        "invoke-expression",
        "icm",
        "invoke-command",
        # Process spawners
        "start-process",
        "saps",
        "start",
        "start-job",
        "sajb",
        "start-threadjob",
        # Event/session code exec
        "register-objectevent",
        "register-engineevent",
        "register-wmievent",
        "register-scheduledjob",
        "new-pssession",
        "nsn",
        "enter-pssession",
        "etsn",
        # .NET escape hatches
        "add-type",
        "new-object",
    ]

    for pattern in patterns:
        if content == pattern:
            return True
        if content == f"{pattern}:*":
            return True
        if content == f"{pattern}*":
            return True
        if content == f"{pattern} *":
            return True
        if content.startswith(f"{pattern} -") and content.endswith("*"):
            return True
        # .exe variants
        sp = pattern.find(" ")
        if sp == -1:
            exe = f"{pattern}.exe"
        else:
            exe = f"{pattern[:sp]}.exe{pattern[sp:]}"
        if content == exe:
            return True
        if content == f"{exe}:*":
            return True
        if content == f"{exe}*":
            return True
        if content == f"{exe} *":
            return True
        if content.startswith(f"{exe} -") and content.endswith("*"):
            return True

    return False


# ---------------------------------------------------------------------------
# isDangerousTaskPermission
# ---------------------------------------------------------------------------

def is_dangerous_task_permission(
    tool_name: str,
    _rule_content: Optional[str],
) -> bool:
    """
    Checks if an Agent (sub-agent) permission rule is dangerous for auto mode.
    Any Agent allow rule would auto-approve sub-agent spawns before the auto mode
    classifier can evaluate the sub-agent's prompt, defeating delegation attack prevention.
    """
    AGENT_TOOL_NAME = _get_agent_tool_name()
    return _normalize_legacy_tool_name(tool_name) == AGENT_TOOL_NAME


# ---------------------------------------------------------------------------
# isDangerousClassifierPermission (private)
# ---------------------------------------------------------------------------

def _is_dangerous_classifier_permission(
    tool_name: str,
    rule_content: Optional[str],
) -> bool:
    """Checks if a permission rule is dangerous for auto mode."""
    if os.environ.get("USER_TYPE") == "ant":
        # Tmux send-keys executes arbitrary shell, bypassing the classifier same as Bash(*)
        if tool_name == "Tmux":
            return True
    return (
        is_dangerous_bash_permission(tool_name, rule_content)
        or is_dangerous_powershell_permission(tool_name, rule_content)
        or is_dangerous_task_permission(tool_name, rule_content)
    )


# ---------------------------------------------------------------------------
# findDangerousClassifierPermissions
# ---------------------------------------------------------------------------

def find_dangerous_classifier_permissions(
    rules: List[PermissionRule],
    cli_allowed_tools: List[str],
) -> List[DangerousPermissionInfo]:
    """
    Finds all dangerous permissions from rules loaded from disk and CLI arguments.
    Returns structured info about each dangerous permission found.
    """
    dangerous: List[DangerousPermissionInfo] = []

    # Check rules loaded from settings
    for rule in rules:
        if rule["ruleBehavior"] == "allow" and _is_dangerous_classifier_permission(
            rule["ruleValue"].get("toolName", ""),
            rule["ruleValue"].get("ruleContent"),
        ):
            rv = rule["ruleValue"]
            rule_content = rv.get("ruleContent")
            rule_string = (
                f"{rv.get('toolName', '')}({rule_content})"
                if rule_content
                else f"{rv.get('toolName', '')}(*)"
            )
            dangerous.append({
                "ruleValue": rv,
                "source": rule["source"],
                "ruleDisplay": rule_string,
                "sourceDisplay": _format_permission_source(rule["source"]),
            })

    # Check CLI --allowed-tools arguments
    for tool_spec in cli_allowed_tools:
        match = re.match(r"^([^(]+)(?:\(([^)]*)\))?$", tool_spec)
        if match:
            tool_name = (match.group(1) or "").strip()
            rule_content = (match.group(2) or "").strip() if match.group(2) is not None else None
            # Empty string ruleContent → treat as None (no content)
            if rule_content == "":
                rule_content = None

            if _is_dangerous_classifier_permission(tool_name, rule_content):
                rv: PermissionRuleValueFull = {"toolName": tool_name}
                if rule_content:
                    rv["ruleContent"] = rule_content
                rule_display = tool_spec if rule_content else f"{tool_name}(*)"
                dangerous.append({
                    "ruleValue": rv,
                    "source": "cliArg",
                    "ruleDisplay": rule_display,
                    "sourceDisplay": "--allowed-tools",
                })

    return dangerous


# ---------------------------------------------------------------------------
# isOverlyBroadBashAllowRule / isOverlyBroadPowerShellAllowRule
# ---------------------------------------------------------------------------

def is_overly_broad_bash_allow_rule(rule_value: PermissionRuleValueFull) -> bool:
    """
    Checks if a Bash allow rule is overly broad (equivalent to YOLO mode).
    Returns True for tool-level Bash allow rules with no content restriction.

    Matches: Bash, Bash(*), Bash() — all parse to { toolName: 'Bash' } with no ruleContent.
    """
    BASH_TOOL_NAME = _get_bash_tool_name()
    return (
        rule_value.get("toolName") == BASH_TOOL_NAME
        and rule_value.get("ruleContent") is None
    )


def is_overly_broad_powershell_allow_rule(rule_value: PermissionRuleValueFull) -> bool:
    """
    PowerShell equivalent of is_overly_broad_bash_allow_rule.

    Matches: PowerShell, PowerShell(*), PowerShell() — all parse to
    { toolName: 'PowerShell' } with no ruleContent.
    """
    POWERSHELL_TOOL_NAME = _get_powershell_tool_name()
    return (
        rule_value.get("toolName") == POWERSHELL_TOOL_NAME
        and rule_value.get("ruleContent") is None
    )


# ---------------------------------------------------------------------------
# findOverlyBroadBashPermissions / findOverlyBroadPowerShellPermissions
# ---------------------------------------------------------------------------

def find_overly_broad_bash_permissions(
    rules: List[PermissionRule],
    cli_allowed_tools: List[str],
) -> List[DangerousPermissionInfo]:
    """
    Finds all overly broad Bash allow rules from settings and CLI arguments.
    An overly broad rule allows ALL bash commands (e.g., Bash or Bash(*)).
    """
    BASH_TOOL_NAME = _get_bash_tool_name()
    overly_broad: List[DangerousPermissionInfo] = []

    for rule in rules:
        if rule["ruleBehavior"] == "allow" and is_overly_broad_bash_allow_rule(rule["ruleValue"]):
            overly_broad.append({
                "ruleValue": rule["ruleValue"],
                "source": rule["source"],
                "ruleDisplay": f"{BASH_TOOL_NAME}(*)",
                "sourceDisplay": _format_permission_source(rule["source"]),
            })

    for tool_spec in cli_allowed_tools:
        parsed = _permission_rule_value_from_string(tool_spec)
        if is_overly_broad_bash_allow_rule(parsed):
            overly_broad.append({
                "ruleValue": parsed,
                "source": "cliArg",
                "ruleDisplay": f"{BASH_TOOL_NAME}(*)",
                "sourceDisplay": "--allowed-tools",
            })

    return overly_broad


def find_overly_broad_powershell_permissions(
    rules: List[PermissionRule],
    cli_allowed_tools: List[str],
) -> List[DangerousPermissionInfo]:
    """PowerShell equivalent of find_overly_broad_bash_permissions."""
    POWERSHELL_TOOL_NAME = _get_powershell_tool_name()
    overly_broad: List[DangerousPermissionInfo] = []

    for rule in rules:
        if rule["ruleBehavior"] == "allow" and is_overly_broad_powershell_allow_rule(rule["ruleValue"]):
            overly_broad.append({
                "ruleValue": rule["ruleValue"],
                "source": rule["source"],
                "ruleDisplay": f"{POWERSHELL_TOOL_NAME}(*)",
                "sourceDisplay": _format_permission_source(rule["source"]),
            })

    for tool_spec in cli_allowed_tools:
        parsed = _permission_rule_value_from_string(tool_spec)
        if is_overly_broad_powershell_allow_rule(parsed):
            overly_broad.append({
                "ruleValue": parsed,
                "source": "cliArg",
                "ruleDisplay": f"{POWERSHELL_TOOL_NAME}(*)",
                "sourceDisplay": "--allowed-tools",
            })

    return overly_broad


# ---------------------------------------------------------------------------
# isPermissionUpdateDestination (type guard)
# ---------------------------------------------------------------------------

_VALID_PERMISSION_UPDATE_DESTINATIONS: Set[str] = {
    "userSettings",
    "projectSettings",
    "localSettings",
    "session",
    "cliArg",
}


def _is_permission_update_destination(source: PermissionRuleSource) -> bool:
    """
    Type guard to check if a PermissionRuleSource is a valid PermissionUpdateDestination.
    Sources like 'flagSettings', 'policySettings', and 'command' are not valid destinations.
    """
    return source in _VALID_PERMISSION_UPDATE_DESTINATIONS


# ---------------------------------------------------------------------------
# removeDangerousPermissions
# ---------------------------------------------------------------------------

def remove_dangerous_permissions(
    context: ToolPermissionContext,
    dangerous_permissions: List[DangerousPermissionInfo],
) -> ToolPermissionContext:
    """
    Removes dangerous permissions from the in-memory context.
    Optionally persists the removal to settings files on disk.
    """
    # Group dangerous rules by their source (destination for updates)
    rules_by_source: Dict[str, List[PermissionRuleValueFull]] = {}
    for perm in dangerous_permissions:
        if not _is_permission_update_destination(perm["source"]):
            continue
        destination = perm["source"]
        if destination not in rules_by_source:
            rules_by_source[destination] = []
        rules_by_source[destination].append(perm["ruleValue"])

    pu_mod = _try_import_permission_update()
    updated_context = context
    for destination, rules in rules_by_source.items():
        if pu_mod and hasattr(pu_mod, "apply_permission_update"):
            updated_context = pu_mod.apply_permission_update(
                updated_context,
                {
                    "type": "removeRules",
                    "rules": rules,
                    "behavior": "allow",
                    "destination": destination,
                },
            )

    return updated_context


# ---------------------------------------------------------------------------
# stripDangerousPermissionsForAutoMode
# ---------------------------------------------------------------------------

def strip_dangerous_permissions_for_auto_mode(
    context: ToolPermissionContext,
) -> ToolPermissionContext:
    """
    Prepares a ToolPermissionContext for auto mode by stripping
    dangerous permissions that would bypass the classifier.
    Returns the cleaned context (with mode unchanged — caller sets the mode).
    """
    rules: List[PermissionRule] = []
    always_allow = context.get("alwaysAllowRules") or {}
    for source, rule_strings in always_allow.items():
        if not rule_strings:
            continue
        for rule_string in rule_strings:
            rule_value = _permission_rule_value_from_string(rule_string)
            rules.append({
                "source": source,
                "ruleBehavior": "allow",
                "ruleValue": rule_value,
            })

    dangerous_permissions = find_dangerous_classifier_permissions(rules, [])
    if not dangerous_permissions:
        return {
            **context,  # type: ignore[misc]
            "strippedDangerousRules": context.get("strippedDangerousRules") or {},
        }

    for permission in dangerous_permissions:
        logger.debug(
            "Ignoring dangerous permission %s from %s (bypasses classifier)",
            permission["ruleDisplay"],
            permission["sourceDisplay"],
        )

    # Build stash of stripped rules (mirrors removeDangerousPermissions source filter)
    stripped: ToolPermissionRulesBySource = {}
    for perm in dangerous_permissions:
        if not _is_permission_update_destination(perm["source"]):
            continue
        existing = stripped.get(perm["source"]) or []  # type: ignore[literal-required]
        existing.append(_permission_rule_value_to_string(perm["ruleValue"]))
        stripped[perm["source"]] = existing  # type: ignore[literal-required]

    return {
        **remove_dangerous_permissions(context, dangerous_permissions),  # type: ignore[misc]
        "strippedDangerousRules": stripped,
    }


# ---------------------------------------------------------------------------
# restoreDangerousPermissions
# ---------------------------------------------------------------------------

def restore_dangerous_permissions(
    context: ToolPermissionContext,
) -> ToolPermissionContext:
    """
    Restores dangerous allow rules previously stashed by
    strip_dangerous_permissions_for_auto_mode. Called when leaving auto mode so that
    the user's Bash(python:*), Agent(*), etc. rules work again in default mode.
    Clears the stash so a second exit is a no-op.
    """
    stash = context.get("strippedDangerousRules")
    if not stash:
        return context

    pu_mod = _try_import_permission_update()
    result = context
    for source, rule_strings in stash.items():
        if not rule_strings:
            continue
        if pu_mod and hasattr(pu_mod, "apply_permission_update"):
            result = pu_mod.apply_permission_update(
                result,
                {
                    "type": "addRules",
                    "rules": [_permission_rule_value_from_string(s) for s in rule_strings],
                    "behavior": "allow",
                    "destination": source,
                },
            )

    return {**result, "strippedDangerousRules": None}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# isAutoModeGateEnabled and related
# ---------------------------------------------------------------------------

def _is_auto_mode_disabled_by_settings() -> bool:
    """Check if auto mode is disabled in settings."""
    settings_mod = _try_import_settings()
    if settings_mod and hasattr(settings_mod, "get_settings_deprecated"):
        settings = settings_mod.get_settings_deprecated() or {}
    else:
        settings = {}
    # Check settings.disableAutoMode or settings.permissions.disableAutoMode
    if settings.get("disableAutoMode") == "disable":
        return True
    perms = settings.get("permissions") or {}
    if isinstance(perms, dict) and perms.get("disableAutoMode") == "disable":
        return True
    return False


def _get_main_loop_model() -> str:
    """Get the main loop model name."""
    mod = _try_import_model()
    if mod and hasattr(mod, "get_main_loop_model"):
        return mod.get_main_loop_model()
    return os.environ.get("ANTHROPIC_MODEL", "")


def _model_supports_auto_mode(model: str) -> bool:
    """Check if the given model supports auto mode."""
    betas_mod = _try_import_betas()
    if betas_mod and hasattr(betas_mod, "model_supports_auto_mode"):
        return betas_mod.model_supports_auto_mode(model)
    return True  # Optimistic default


def is_auto_mode_gate_enabled() -> bool:
    """
    Checks if auto mode can be entered: circuit breaker is not active and settings
    have not disabled it. Synchronous.
    """
    auto_mode_mod = _try_import_auto_mode_state()
    if auto_mode_mod and hasattr(auto_mode_mod, "is_auto_mode_circuit_broken"):
        if auto_mode_mod.is_auto_mode_circuit_broken():
            return False
    if _is_auto_mode_disabled_by_settings():
        return False
    if not _model_supports_auto_mode(_get_main_loop_model()):
        return False
    return True


def get_auto_mode_unavailable_reason() -> Optional[AutoModeUnavailableReason]:
    """
    Returns the reason auto mode is currently unavailable, or None if available.
    Synchronous — uses state populated by verify_auto_mode_gate_access.
    """
    if _is_auto_mode_disabled_by_settings():
        return "settings"
    auto_mode_mod = _try_import_auto_mode_state()
    if auto_mode_mod and hasattr(auto_mode_mod, "is_auto_mode_circuit_broken"):
        if auto_mode_mod.is_auto_mode_circuit_broken():
            return "circuit-breaker"
    if not _model_supports_auto_mode(_get_main_loop_model()):
        return "model"
    return None


def get_auto_mode_unavailable_notification(reason: AutoModeUnavailableReason) -> str:
    """Return user-facing notification string for auto mode unavailability."""
    base: str
    if reason == "settings":
        base = "auto mode disabled by settings"
    elif reason == "circuit-breaker":
        base = "auto mode is unavailable for your plan"
    else:
        base = "auto mode unavailable for this model"

    if os.environ.get("USER_TYPE") == "ant":
        return f"{base} · #claude-code-feedback"
    return base


# ---------------------------------------------------------------------------
# AutoModeEnabledState helpers
# ---------------------------------------------------------------------------

def parse_auto_mode_enabled_state(value: Any) -> AutoModeEnabledState:
    """Parse the enabled state from a GrowthBook config value."""
    if value in ("enabled", "disabled", "opt-in"):
        return value  # type: ignore[return-value]
    return AUTO_MODE_ENABLED_DEFAULT


def get_auto_mode_enabled_state() -> AutoModeEnabledState:
    """
    Reads the `enabled` field from tengu_auto_mode_config (cached, may be stale).
    Defaults to 'disabled' if GrowthBook is unavailable or the field is unset.
    """
    gb_mod = _try_import_growthbook()
    if gb_mod and hasattr(gb_mod, "get_feature_value_cached_may_be_stale"):
        config = gb_mod.get_feature_value_cached_may_be_stale("tengu_auto_mode_config", {})
        return parse_auto_mode_enabled_state(config.get("enabled") if isinstance(config, dict) else None)
    return AUTO_MODE_ENABLED_DEFAULT


_NO_CACHED_AUTO_MODE_CONFIG = object()


def get_auto_mode_enabled_state_if_cached() -> Optional[AutoModeEnabledState]:
    """
    Like get_auto_mode_enabled_state but returns None when no cached value
    exists (cold start, before GrowthBook init). Used by the sync
    circuit-breaker check in initial_permission_mode_from_cli.
    """
    gb_mod = _try_import_growthbook()
    if gb_mod and hasattr(gb_mod, "get_feature_value_cached_may_be_stale"):
        config = gb_mod.get_feature_value_cached_may_be_stale(
            "tengu_auto_mode_config", _NO_CACHED_AUTO_MODE_CONFIG
        )
        if config is _NO_CACHED_AUTO_MODE_CONFIG:
            return None
        return parse_auto_mode_enabled_state(config.get("enabled") if isinstance(config, dict) else None)
    return None


def has_auto_mode_opt_in_any_source() -> bool:
    """
    Returns True if the user has opted in to auto mode via any trusted mechanism:
    - CLI flag (--enable-auto-mode / --permission-mode auto) — session-scoped
    - skipAutoPermissionPrompt setting (persistent)
    """
    auto_mode_mod = _try_import_auto_mode_state()
    if auto_mode_mod and hasattr(auto_mode_mod, "get_auto_mode_flag_cli"):
        if auto_mode_mod.get_auto_mode_flag_cli():
            return True
    settings_mod = _try_import_settings()
    if settings_mod and hasattr(settings_mod, "has_auto_mode_opt_in"):
        return settings_mod.has_auto_mode_opt_in()
    return False


# ---------------------------------------------------------------------------
# verifyAutoModeGateAccess (async)
# ---------------------------------------------------------------------------

async def verify_auto_mode_gate_access(
    current_context: ToolPermissionContext,
    fast_mode: Optional[bool] = None,
) -> AutoModeGateCheckResult:
    """
    Async check of auto mode availability.

    Returns a transform function (not a pre-computed context) that callers
    apply inside set_app_state against the CURRENT context. This prevents the
    async GrowthBook await from clobbering mid-turn mode changes.
    """
    gb_mod = _try_import_growthbook()
    auto_mode_config: Dict[str, Any] = {}
    if gb_mod and hasattr(gb_mod, "get_dynamic_config_blocks_on_init"):
        try:
            auto_mode_config = await gb_mod.get_dynamic_config_blocks_on_init(
                "tengu_auto_mode_config", {}
            ) or {}
        except Exception:
            pass

    enabled_state = parse_auto_mode_enabled_state(auto_mode_config.get("enabled"))
    disabled_by_settings = _is_auto_mode_disabled_by_settings()

    # Update circuit breaker state
    auto_mode_mod = _try_import_auto_mode_state()
    if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_circuit_broken"):
        auto_mode_mod.set_auto_mode_circuit_broken(
            enabled_state == "disabled" or disabled_by_settings
        )

    # Check model support
    main_model = _get_main_loop_model()
    disable_fast_mode_breaker_fires = bool(
        auto_mode_config.get("disableFastMode")
        and (
            fast_mode
            or (
                os.environ.get("USER_TYPE") == "ant"
                and "-fast" in main_model.lower()
            )
        )
    )
    model_supported = _model_supports_auto_mode(main_model) and not disable_fast_mode_breaker_fires

    carousel_available = False
    if enabled_state != "disabled" and not disabled_by_settings and model_supported:
        carousel_available = enabled_state == "enabled" or has_auto_mode_opt_in_any_source()

    can_enter_auto = (
        enabled_state != "disabled" and not disabled_by_settings and model_supported
    )

    logger.debug(
        "[auto-mode] verify_auto_mode_gate_access: "
        "enabled_state=%s disabled_by_settings=%s model=%s model_supported=%s "
        "carousel_available=%s can_enter_auto=%s",
        enabled_state, disabled_by_settings, main_model, model_supported,
        carousel_available, can_enter_auto,
    )

    auto_mode_flag_cli = False
    if auto_mode_mod and hasattr(auto_mode_mod, "get_auto_mode_flag_cli"):
        auto_mode_flag_cli = auto_mode_mod.get_auto_mode_flag_cli()

    def _set_available(ctx: ToolPermissionContext, available: bool) -> ToolPermissionContext:
        if ctx.get("isAutoModeAvailable") != available:
            logger.debug(
                "[auto-mode] verify_auto_mode_gate_access setAvailable: %s -> %s",
                ctx.get("isAutoModeAvailable"), available,
            )
        if ctx.get("isAutoModeAvailable") == available:
            return ctx
        return {**ctx, "isAutoModeAvailable": available}  # type: ignore[misc]

    if can_enter_auto:
        def _update_ctx_available(ctx: ToolPermissionContext) -> ToolPermissionContext:
            return _set_available(ctx, carousel_available)
        return {"updateContext": _update_ctx_available}

    # Gate is off — determine reason
    reason: AutoModeUnavailableReason
    if disabled_by_settings:
        reason = "settings"
        logger.warning("auto mode disabled: disableAutoMode in settings")
    elif enabled_state == "disabled":
        reason = "circuit-breaker"
        logger.warning("auto mode disabled: tengu_auto_mode_config.enabled === 'disabled' (circuit breaker)")
    else:
        reason = "model"
        logger.warning("auto mode disabled: model %s does not support auto mode", main_model)

    notification = get_auto_mode_unavailable_notification(reason)

    # Unified kick-out transform
    def _kick_out_of_auto_if_needed(ctx: ToolPermissionContext) -> ToolPermissionContext:
        in_auto = ctx.get("mode") == "auto"
        logger.debug(
            "[auto-mode] kick_out_of_auto_if_needed: ctx.mode=%s ctx.prePlanMode=%s reason=%s",
            ctx.get("mode"), ctx.get("prePlanMode"), reason,
        )
        in_plan_with_auto_active = (
            ctx.get("mode") == "plan"
            and (ctx.get("prePlanMode") == "auto" or bool(ctx.get("strippedDangerousRules")))
        )
        if not in_auto and not in_plan_with_auto_active:
            return _set_available(ctx, False)

        pu_mod = _try_import_permission_update()
        bootstrap_mod = _try_import_bootstrap_state()

        if in_auto:
            if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_active"):
                auto_mode_mod.set_auto_mode_active(False)
            if bootstrap_mod and hasattr(bootstrap_mod, "set_needs_auto_mode_exit_attachment"):
                bootstrap_mod.set_needs_auto_mode_exit_attachment(True)
            restored = restore_dangerous_permissions(ctx)
            if pu_mod and hasattr(pu_mod, "apply_permission_update"):
                restored = pu_mod.apply_permission_update(
                    restored,
                    {"type": "setMode", "mode": "default", "destination": "session"},
                )
            return {**restored, "isAutoModeAvailable": False}  # type: ignore[misc]

        # Plan with auto active
        if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_active"):
            auto_mode_mod.set_auto_mode_active(False)
        if bootstrap_mod and hasattr(bootstrap_mod, "set_needs_auto_mode_exit_attachment"):
            bootstrap_mod.set_needs_auto_mode_exit_attachment(True)
        pre_plan = ctx.get("prePlanMode")
        return {
            **restore_dangerous_permissions(ctx),  # type: ignore[misc]
            "prePlanMode": "default" if pre_plan == "auto" else pre_plan,
            "isAutoModeAvailable": False,
        }

    was_in_auto = current_context.get("mode") == "auto"
    auto_active_during_plan = (
        current_context.get("mode") == "plan"
        and (
            current_context.get("prePlanMode") == "auto"
            or bool(current_context.get("strippedDangerousRules"))
        )
    )
    wanted_auto = was_in_auto or auto_active_during_plan or auto_mode_flag_cli

    if not wanted_auto:
        return {"updateContext": _kick_out_of_auto_if_needed}

    if was_in_auto or auto_active_during_plan:
        return {"updateContext": _kick_out_of_auto_if_needed, "notification": notification}

    # autoModeFlagCli only
    return {
        "updateContext": _kick_out_of_auto_if_needed,
        "notification": notification if current_context.get("isAutoModeAvailable") else None,
    }


# ---------------------------------------------------------------------------
# shouldDisableBypassPermissions (async)
# ---------------------------------------------------------------------------

async def should_disable_bypass_permissions() -> bool:
    """Core logic to check if bypassPermissions should be disabled based on Statsig gate."""
    gb_mod = _try_import_growthbook()
    if gb_mod and hasattr(gb_mod, "check_security_restriction_gate"):
        return await gb_mod.check_security_restriction_gate("tengu_disable_bypass_permissions_mode")
    return False


def is_bypass_permissions_mode_disabled() -> bool:
    """
    Checks if bypassPermissions mode is currently disabled by Statsig gate or settings.
    Synchronous version using cached Statsig values.
    """
    gb_mod = _try_import_growthbook()
    gb_disable = False
    if gb_mod and hasattr(gb_mod, "check_statsig_feature_gate_cached_may_be_stale"):
        gb_disable = gb_mod.check_statsig_feature_gate_cached_may_be_stale(
            "tengu_disable_bypass_permissions_mode"
        )

    settings_mod = _try_import_settings()
    settings: Dict[str, Any] = {}
    if settings_mod and hasattr(settings_mod, "get_settings_deprecated"):
        settings = settings_mod.get_settings_deprecated() or {}
    perms = settings.get("permissions") or {}
    settings_disable = isinstance(perms, dict) and perms.get("disableBypassPermissionsMode") == "disable"

    return gb_disable or settings_disable


def create_disabled_bypass_permissions_context(
    current_context: ToolPermissionContext,
) -> ToolPermissionContext:
    """Creates an updated context with bypassPermissions disabled."""
    pu_mod = _try_import_permission_update()
    updated_context = current_context
    if current_context.get("mode") == "bypassPermissions":
        if pu_mod and hasattr(pu_mod, "apply_permission_update"):
            updated_context = pu_mod.apply_permission_update(
                current_context,
                {"type": "setMode", "mode": "default", "destination": "session"},
            )
    return {**updated_context, "isBypassPermissionsModeAvailable": False}  # type: ignore[misc]


async def check_and_disable_bypass_permissions(
    current_context: ToolPermissionContext,
) -> None:
    """
    Asynchronously checks if the bypassPermissions mode should be disabled based on Statsig gate
    and returns an updated toolPermissionContext if needed.
    """
    if not current_context.get("isBypassPermissionsModeAvailable"):
        return

    should_disable = await should_disable_bypass_permissions()
    if not should_disable:
        return

    logger.warning(
        "bypassPermissions mode is being disabled by Statsig gate (async check)"
    )

    gs_mod = _try_import_graceful_shutdown()
    if gs_mod and hasattr(gs_mod, "graceful_shutdown"):
        await gs_mod.graceful_shutdown(1, "bypass_permissions_disabled")


# ---------------------------------------------------------------------------
# isDangerousBashPermission-related public API
# ---------------------------------------------------------------------------

def is_default_permission_mode_auto() -> bool:
    """Check if the default permission mode is set to 'auto' in settings."""
    settings_mod = _try_import_settings()
    if settings_mod and hasattr(settings_mod, "get_settings_deprecated"):
        settings = settings_mod.get_settings_deprecated() or {}
        perms = settings.get("permissions") or {}
        return isinstance(perms, dict) and perms.get("defaultMode") == "auto"
    return False


def should_plan_use_auto_mode() -> bool:
    """
    Whether plan mode should use auto mode semantics (classifier runs during
    plan). True when the user has opted in to auto mode and the gate is enabled.
    Evaluated at permission-check time so it's reactive to config changes.
    """
    settings_mod = _try_import_settings()
    if not (settings_mod and hasattr(settings_mod, "get_use_auto_mode_during_plan")):
        return False

    has_opt_in = False
    if settings_mod and hasattr(settings_mod, "has_auto_mode_opt_in"):
        has_opt_in = settings_mod.has_auto_mode_opt_in()

    return (
        has_opt_in
        and is_auto_mode_gate_enabled()
        and settings_mod.get_use_auto_mode_during_plan()
    )


# ---------------------------------------------------------------------------
# prepareContextForPlanMode
# ---------------------------------------------------------------------------

def prepare_context_for_plan_mode(
    context: ToolPermissionContext,
) -> ToolPermissionContext:
    """
    Centralized plan-mode entry. Stashes the current mode as prePlanMode so
    ExitPlanMode can restore it. When the user has opted in to auto mode,
    auto semantics stay active during plan mode.
    """
    current_mode = context.get("mode", "default")
    if current_mode == "plan":
        return context

    auto_mode_mod = _try_import_auto_mode_state()
    bootstrap_mod = _try_import_bootstrap_state()

    plan_auto_mode = should_plan_use_auto_mode()

    if current_mode == "auto":
        if plan_auto_mode:
            return {**context, "prePlanMode": "auto"}  # type: ignore[misc]
        if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_active"):
            auto_mode_mod.set_auto_mode_active(False)
        if bootstrap_mod and hasattr(bootstrap_mod, "set_needs_auto_mode_exit_attachment"):
            bootstrap_mod.set_needs_auto_mode_exit_attachment(True)
        return {
            **restore_dangerous_permissions(context),  # type: ignore[misc]
            "prePlanMode": "auto",
        }

    if plan_auto_mode and current_mode != "bypassPermissions":
        if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_active"):
            auto_mode_mod.set_auto_mode_active(True)
        return {
            **strip_dangerous_permissions_for_auto_mode(context),  # type: ignore[misc]
            "prePlanMode": current_mode,
        }

    logger.debug(
        "[prepare_context_for_plan_mode] plain plan entry, prePlanMode=%s", current_mode
    )
    return {**context, "prePlanMode": current_mode}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# transitionPlanAutoMode
# ---------------------------------------------------------------------------

def transition_plan_auto_mode(
    context: ToolPermissionContext,
) -> ToolPermissionContext:
    """
    Reconciles auto-mode state during plan mode after a settings change.
    Compares desired state (should_plan_use_auto_mode) against actual state
    (is_auto_mode_active) and activates/deactivates auto accordingly.
    No-op when not in plan mode.
    """
    if context.get("mode") != "plan":
        return context
    # Mirror prepare_context_for_plan_mode's entry-time exclusion
    if context.get("prePlanMode") == "bypassPermissions":
        return context

    auto_mode_mod = _try_import_auto_mode_state()
    bootstrap_mod = _try_import_bootstrap_state()

    want = should_plan_use_auto_mode()
    have = False
    if auto_mode_mod and hasattr(auto_mode_mod, "is_auto_mode_active"):
        have = auto_mode_mod.is_auto_mode_active()

    if want and have:
        # Re-strip so the classifier isn't bypassed by prefix-rule allow matches
        return strip_dangerous_permissions_for_auto_mode(context)

    if not want and not have:
        return context

    if want:
        if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_active"):
            auto_mode_mod.set_auto_mode_active(True)
        if bootstrap_mod and hasattr(bootstrap_mod, "set_needs_auto_mode_exit_attachment"):
            bootstrap_mod.set_needs_auto_mode_exit_attachment(False)
        return strip_dangerous_permissions_for_auto_mode(context)

    if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_active"):
        auto_mode_mod.set_auto_mode_active(False)
    if bootstrap_mod and hasattr(bootstrap_mod, "set_needs_auto_mode_exit_attachment"):
        bootstrap_mod.set_needs_auto_mode_exit_attachment(True)
    return restore_dangerous_permissions(context)


# ---------------------------------------------------------------------------
# transitionPermissionMode
# ---------------------------------------------------------------------------

def transition_permission_mode(
    from_mode: str,
    to_mode: str,
    context: ToolPermissionContext,
) -> ToolPermissionContext:
    """
    Handles all state transitions when switching permission modes.
    Centralises side-effects so that every activation path behaves identically.

    Currently handles:
    - Plan mode enter/exit attachments (via handle_plan_mode_transition)
    - Auto mode activation: set_auto_mode_active, strip_dangerous_permissions_for_auto_mode

    Returns the (possibly modified) context. Caller is responsible for setting
    the mode on the returned context.
    """
    # plan→plan (SDK set_permission_mode) would wrongly hit the leave branch
    if from_mode == to_mode:
        return context

    bootstrap_mod = _try_import_bootstrap_state()
    auto_mode_mod = _try_import_auto_mode_state()

    if bootstrap_mod:
        if hasattr(bootstrap_mod, "handle_plan_mode_transition"):
            bootstrap_mod.handle_plan_mode_transition(from_mode, to_mode)
        if hasattr(bootstrap_mod, "handle_auto_mode_transition"):
            bootstrap_mod.handle_auto_mode_transition(from_mode, to_mode)

    if from_mode == "plan" and to_mode != "plan":
        if bootstrap_mod and hasattr(bootstrap_mod, "set_has_exited_plan_mode"):
            bootstrap_mod.set_has_exited_plan_mode(True)

    # Plan mode with auto active counts as using the classifier (for the leaving side).
    is_auto_mode_active = False
    if auto_mode_mod and hasattr(auto_mode_mod, "is_auto_mode_active"):
        is_auto_mode_active = auto_mode_mod.is_auto_mode_active()

    from_uses_classifier = from_mode == "auto" or (
        from_mode == "plan" and is_auto_mode_active
    )
    to_uses_classifier = to_mode == "auto"  # plan entry handled in the block below

    if to_mode == "plan" and from_mode != "plan":
        return prepare_context_for_plan_mode(context)

    if to_uses_classifier and not from_uses_classifier:
        if not is_auto_mode_gate_enabled():
            raise ValueError("Cannot transition to auto mode: gate is not enabled")
        if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_active"):
            auto_mode_mod.set_auto_mode_active(True)
        context = strip_dangerous_permissions_for_auto_mode(context)
    elif from_uses_classifier and not to_uses_classifier:
        if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_active"):
            auto_mode_mod.set_auto_mode_active(False)
        if bootstrap_mod and hasattr(bootstrap_mod, "set_needs_auto_mode_exit_attachment"):
            bootstrap_mod.set_needs_auto_mode_exit_attachment(True)
        context = restore_dangerous_permissions(context)

    # Only spread if there's something to clear (preserves ref equality)
    if from_mode == "plan" and to_mode != "plan" and context.get("prePlanMode"):
        return {**context, "prePlanMode": None}  # type: ignore[misc]

    return context


# ---------------------------------------------------------------------------
# parseToolListFromCLI
# ---------------------------------------------------------------------------

def parse_tool_list_from_cli(tools: List[str]) -> List[str]:
    """
    Parse a list of CLI tool strings into individual tool names.
    Handles both comma-separated and space-separated formats.
    """
    if not tools:
        return []

    result: List[str] = []

    for tool_string in tools:
        if not tool_string:
            continue

        current = ""
        is_in_parens = False

        for char in tool_string:
            if char == "(":
                is_in_parens = True
                current += char
            elif char == ")":
                is_in_parens = False
                current += char
            elif char == ",":
                if is_in_parens:
                    current += char
                else:
                    if current.strip():
                        result.append(current.strip())
                    current = ""
            elif char == " ":
                if is_in_parens:
                    current += char
                elif current.strip():
                    result.append(current.strip())
                    current = ""
            else:
                current += char

        if current.strip():
            result.append(current.strip())

    return result


# ---------------------------------------------------------------------------
# parseBaseToolsFromCLI
# ---------------------------------------------------------------------------

def parse_base_tools_from_cli(base_tools: List[str]) -> List[str]:
    """
    Parse base tools specification from CLI.
    Handles both preset names (default, none) and custom tool lists.
    """
    tools_mod = _try_import_tools_module()
    joined_input = " ".join(base_tools).strip()

    if tools_mod:
        if hasattr(tools_mod, "parse_tool_preset"):
            preset = tools_mod.parse_tool_preset(joined_input)
            if preset:
                if hasattr(tools_mod, "get_tools_for_default_preset"):
                    return tools_mod.get_tools_for_default_preset()
                return []

    return parse_tool_list_from_cli(base_tools)


# ---------------------------------------------------------------------------
# initialPermissionModeFromCLI
# ---------------------------------------------------------------------------

def _get_permission_mode_from_string(mode_str: str) -> str:
    """Convert a CLI mode string to a canonical PermissionMode."""
    try:
        from claude_code.utils.permissions.permission_mode import permission_mode_from_string  # type: ignore[import]
        return permission_mode_from_string(mode_str)
    except ImportError:
        return mode_str


def initial_permission_mode_from_cli(
    permission_mode_cli: Optional[str],
    dangerously_skip_permissions: Optional[bool],
) -> Dict[str, Any]:
    """
    Safely convert CLI flags to a PermissionMode.
    Returns a dict with 'mode' and optional 'notification'.
    """
    settings_mod = _try_import_settings()
    gb_mod = _try_import_growthbook()
    auto_mode_mod = _try_import_auto_mode_state()

    settings: Dict[str, Any] = {}
    if settings_mod and hasattr(settings_mod, "get_settings_deprecated"):
        settings = settings_mod.get_settings_deprecated() or {}

    # Check GrowthBook gate first - highest precedence
    gb_disable = False
    if gb_mod and hasattr(gb_mod, "check_statsig_feature_gate_cached_may_be_stale"):
        gb_disable = gb_mod.check_statsig_feature_gate_cached_may_be_stale(
            "tengu_disable_bypass_permissions_mode"
        )

    # Then check settings - lower precedence
    perms_config = settings.get("permissions") or {}
    settings_disable = isinstance(perms_config, dict) and perms_config.get("disableBypassPermissionsMode") == "disable"

    # Statsig gate takes precedence over settings
    disable_bypass_permissions_mode = gb_disable or settings_disable

    # Sync circuit-breaker check
    auto_mode_circuit_broken_sync = (
        get_auto_mode_enabled_state_if_cached() == "disabled"
    )

    # Modes in order of priority
    ordered_modes: List[str] = []
    notification: Optional[str] = None

    if dangerously_skip_permissions:
        ordered_modes.append("bypassPermissions")

    if permission_mode_cli:
        parsed_mode = _get_permission_mode_from_string(permission_mode_cli)
        if parsed_mode == "auto":
            if not auto_mode_circuit_broken_sync:
                ordered_modes.append("auto")
            else:
                logger.warning("auto mode circuit breaker active (cached) — falling back to default")
        else:
            ordered_modes.append(parsed_mode)

    settings_mode = (
        perms_config.get("defaultMode")
        if isinstance(perms_config, dict)
        else None
    )
    if settings_mode:
        if os.environ.get("CLAUDE_CODE_REMOTE") and os.environ.get("CLAUDE_CODE_REMOTE", "").lower() not in ("0", "false", ""):
            if settings_mode not in ("acceptEdits", "plan", "default"):
                logger.warning(
                    'settings defaultMode "%s" is not supported in CLAUDE_CODE_REMOTE — only acceptEdits and plan are allowed',
                    settings_mode,
                )
                settings_mode = None

        if settings_mode == "auto":
            if not auto_mode_circuit_broken_sync:
                ordered_modes.append("auto")
            else:
                logger.warning("auto mode circuit breaker active (cached) — falling back to default")
        elif settings_mode:
            ordered_modes.append(settings_mode)

    result: Optional[Dict[str, Any]] = None
    for mode in ordered_modes:
        if mode == "bypassPermissions" and disable_bypass_permissions_mode:
            if gb_disable:
                logger.warning("bypassPermissions mode is disabled by Statsig gate")
                notification = "Bypass permissions mode was disabled by your organization policy"
            else:
                logger.warning("bypassPermissions mode is disabled by settings")
                notification = "Bypass permissions mode was disabled by settings"
            continue
        result = {"mode": mode, "notification": notification}
        break

    if not result:
        result = {"mode": "default", "notification": notification}

    if result.get("mode") == "auto":
        if auto_mode_mod and hasattr(auto_mode_mod, "set_auto_mode_active"):
            auto_mode_mod.set_auto_mode_active(True)

    return result


# ---------------------------------------------------------------------------
# isSymlinkTo helper
# ---------------------------------------------------------------------------

def _is_symlink_to(*, process_pwd: str, original_cwd: str) -> bool:
    """Check if process_pwd is a symlink that resolves to original_cwd."""
    fs_mod = _try_import_fs_operations()
    if fs_mod and hasattr(fs_mod, "safe_resolve_path"):
        resolved_path, is_symlink = fs_mod.safe_resolve_path(process_pwd)
        if is_symlink:
            return resolved_path == os.path.realpath(original_cwd)
    else:
        # Fallback: check using os
        if os.path.islink(process_pwd):
            return os.path.realpath(process_pwd) == os.path.realpath(original_cwd)
    return False


# ---------------------------------------------------------------------------
# initializeToolPermissionContext (async)
# ---------------------------------------------------------------------------

async def initialize_tool_permission_context(
    allowed_tools_cli: List[str],
    disallowed_tools_cli: List[str],
    base_tools_cli: Optional[List[str]],
    permission_mode: str,
    allow_dangerously_skip_permissions: bool,
    add_dirs: List[str],
) -> Dict[str, Any]:
    """
    Initialize a ToolPermissionContext from CLI arguments and settings.

    Returns:
        dict with keys: toolPermissionContext, warnings,
                        dangerousPermissions, overlyBroadBashPermissions
    """
    pl_mod = _try_import_permissions_loader()
    pu_mod = _try_import_permission_update()
    permissions_mod = _try_import_permissions()
    gb_mod = _try_import_growthbook()
    settings_mod = _try_import_settings()
    add_dir_validation_mod = _try_import_add_dir_validation()
    bootstrap_mod = _try_import_bootstrap_state()
    tools_mod = _try_import_tools_module()

    # Parse and normalize CLI tool rules
    parsed_allowed_tools_cli = [
        _permission_rule_value_to_string(_permission_rule_value_from_string(rule))
        for rule in parse_tool_list_from_cli(allowed_tools_cli)
    ]

    parsed_disallowed_tools_cli = parse_tool_list_from_cli(disallowed_tools_cli)

    # If base tools are specified, automatically deny all tools NOT in the base set
    if base_tools_cli and len(base_tools_cli) > 0:
        base_tools_result = parse_base_tools_from_cli(base_tools_cli)
        base_tools_set = {_normalize_legacy_tool_name(t) for t in base_tools_result}
        all_tool_names: List[str] = []
        if tools_mod and hasattr(tools_mod, "get_tools_for_default_preset"):
            all_tool_names = tools_mod.get_tools_for_default_preset()
        tools_to_disallow = [t for t in all_tool_names if t not in base_tools_set]
        parsed_disallowed_tools_cli = [*parsed_disallowed_tools_cli, *tools_to_disallow]

    warnings: List[str] = []

    # Additional working directories
    additional_working_directories: Dict[str, Any] = {}
    original_cwd = ""
    if bootstrap_mod and hasattr(bootstrap_mod, "get_original_cwd"):
        original_cwd = bootstrap_mod.get_original_cwd()

    process_pwd = os.environ.get("PWD", "")
    if process_pwd and process_pwd != original_cwd and original_cwd:
        if _is_symlink_to(process_pwd=process_pwd, original_cwd=original_cwd):
            additional_working_directories[process_pwd] = {
                "path": process_pwd,
                "source": "session",
            }

    # Check if bypassPermissions mode is available
    gb_disable = False
    if gb_mod and hasattr(gb_mod, "check_statsig_feature_gate_cached_may_be_stale"):
        gb_disable = gb_mod.check_statsig_feature_gate_cached_may_be_stale(
            "tengu_disable_bypass_permissions_mode"
        )

    settings: Dict[str, Any] = {}
    if settings_mod and hasattr(settings_mod, "get_settings_deprecated"):
        settings = settings_mod.get_settings_deprecated() or {}

    perms_config = settings.get("permissions") or {}
    settings_disable = isinstance(perms_config, dict) and perms_config.get("disableBypassPermissionsMode") == "disable"

    is_bypass_permissions_mode_available = (
        (permission_mode == "bypassPermissions" or allow_dangerously_skip_permissions)
        and not gb_disable
        and not settings_disable
    )

    # Load all permission rules from disk
    rules_from_disk: List[PermissionRule] = []
    if pl_mod and hasattr(pl_mod, "load_all_permission_rules_from_disk"):
        rules_from_disk = pl_mod.load_all_permission_rules_from_disk()

    # Ant-only: Detect overly broad shell allow rules for all modes
    overly_broad_bash_permissions: List[DangerousPermissionInfo] = []
    is_ant = os.environ.get("USER_TYPE") == "ant"
    is_remote = os.environ.get("CLAUDE_CODE_REMOTE", "").lower() not in ("", "0", "false")
    is_local_agent = os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "local-agent"

    if is_ant and not is_remote and not is_local_agent:
        overly_broad_bash_permissions = [
            *find_overly_broad_bash_permissions(rules_from_disk, parsed_allowed_tools_cli),
            *find_overly_broad_powershell_permissions(rules_from_disk, parsed_allowed_tools_cli),
        ]

    # Ant-only: Detect dangerous shell permissions for auto mode
    dangerous_permissions: List[DangerousPermissionInfo] = []
    if permission_mode == "auto":
        dangerous_permissions = find_dangerous_classifier_permissions(
            rules_from_disk, parsed_allowed_tools_cli
        )

    # Build initial permission context
    initial_context: ToolPermissionContext = {
        "mode": permission_mode,
        "additionalWorkingDirectories": additional_working_directories,
        "alwaysAllowRules": {"cliArg": parsed_allowed_tools_cli},
        "alwaysDenyRules": {"cliArg": parsed_disallowed_tools_cli},
        "alwaysAskRules": {},
        "isBypassPermissionsModeAvailable": is_bypass_permissions_mode_available,
        "isAutoModeAvailable": is_auto_mode_gate_enabled(),
    }

    # Apply rules from disk
    tool_permission_context: ToolPermissionContext
    if permissions_mod and hasattr(permissions_mod, "apply_permission_rules_to_permission_context"):
        tool_permission_context = permissions_mod.apply_permission_rules_to_permission_context(
            initial_context, rules_from_disk
        )
    else:
        tool_permission_context = initial_context

    # Add directories from settings and --add-dir
    all_additional_directories: List[str] = []
    if isinstance(perms_config, dict):
        all_additional_directories.extend(perms_config.get("additionalDirectories") or [])
    all_additional_directories.extend(add_dirs)

    if add_dir_validation_mod and hasattr(add_dir_validation_mod, "validate_directory_for_workspace"):
        import asyncio

        validation_results = await asyncio.gather(
            *[
                add_dir_validation_mod.validate_directory_for_workspace(
                    directory, tool_permission_context
                )
                for directory in all_additional_directories
            ]
        )
        for result in validation_results:
            result_type = result.get("resultType") if isinstance(result, dict) else getattr(result, "resultType", None)
            if result_type == "success":
                abs_path = result.get("absolutePath") if isinstance(result, dict) else getattr(result, "absolutePath", None)
                if abs_path and pu_mod and hasattr(pu_mod, "apply_permission_update"):
                    tool_permission_context = pu_mod.apply_permission_update(
                        tool_permission_context,
                        {
                            "type": "addDirectories",
                            "directories": [abs_path],
                            "destination": "cliArg",
                        },
                    )
            elif result_type not in ("alreadyInWorkingDirectory", "pathNotFound", None):
                if hasattr(add_dir_validation_mod, "add_dir_help_message"):
                    warnings.append(add_dir_validation_mod.add_dir_help_message(result))

    return {
        "toolPermissionContext": tool_permission_context,
        "warnings": warnings,
        "dangerousPermissions": dangerous_permissions,
        "overlyBroadBashPermissions": overly_broad_bash_permissions,
    }
