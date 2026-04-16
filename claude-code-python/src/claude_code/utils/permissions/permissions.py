"""
permissions.py — Permission pipeline for tool use decisions.

Ported from: utils/permissions/permissions.ts (1486 lines)
"""
from __future__ import annotations

import logging
from typing import (
    TYPE_CHECKING,
    Any,
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

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLASSIFIER_FAIL_CLOSED_REFRESH_MS = 30 * 60 * 1000  # 30 minutes

# All known permission rule sources (ordered from highest to lowest priority).
PERMISSION_RULE_SOURCES: Tuple[str, ...] = (
    "policySettings",
    "flagSettings",
    "userSettings",
    "projectSettings",
    "localSettings",
    "cliArg",
    "command",
    "session",
)

# ---------------------------------------------------------------------------
# Type definitions (TypedDicts mirroring the TS interfaces)
# ---------------------------------------------------------------------------


class PermissionRuleValue(TypedDict, total=False):
    """Content of a permission rule (toolName + optional ruleContent)."""
    toolName: str
    ruleContent: Optional[str]  # type: ignore[misc]


class _PermissionRuleValueRequired(TypedDict):
    toolName: str


class PermissionRuleValueFull(_PermissionRuleValueRequired, total=False):
    ruleContent: str


PermissionBehavior = Literal["allow", "deny", "ask"]
PermissionRuleSource = str  # one of PERMISSION_RULE_SOURCES


class PermissionRule(TypedDict):
    source: PermissionRuleSource
    ruleBehavior: PermissionBehavior
    ruleValue: PermissionRuleValueFull


# PermissionDecisionReason variants
class _ReasonRule(TypedDict):
    type: Literal["rule"]
    rule: PermissionRule


class _ReasonHook(TypedDict, total=False):
    type: Literal["hook"]
    hookName: str
    reason: Optional[str]


class _ReasonClassifier(TypedDict):
    type: Literal["classifier"]
    classifier: str
    reason: str


class _ReasonMode(TypedDict):
    type: Literal["mode"]
    mode: str


class _ReasonSafetyCheck(TypedDict, total=False):
    type: Literal["safetyCheck"]
    reason: str
    classifierApprovable: Optional[bool]


class _ReasonOther(TypedDict):
    type: Literal["other"]
    reason: str


class _ReasonAsyncAgent(TypedDict):
    type: Literal["asyncAgent"]
    reason: str


class _ReasonPermissionPromptTool(TypedDict):
    type: Literal["permissionPromptTool"]
    permissionPromptToolName: str


class _ReasonSubcommandResults(TypedDict):
    type: Literal["subcommandResults"]
    reasons: List[Tuple[str, Any]]


class _ReasonSandboxOverride(TypedDict):
    type: Literal["sandboxOverride"]


class _ReasonWorkingDir(TypedDict):
    type: Literal["workingDir"]
    reason: str


PermissionDecisionReason = Union[
    _ReasonRule,
    _ReasonHook,
    _ReasonClassifier,
    _ReasonMode,
    _ReasonSafetyCheck,
    _ReasonOther,
    _ReasonAsyncAgent,
    _ReasonPermissionPromptTool,
    _ReasonSubcommandResults,
    _ReasonSandboxOverride,
    _ReasonWorkingDir,
]


class PermissionAllowDecision(TypedDict, total=False):
    behavior: Literal["allow"]
    updatedInput: Optional[Dict[str, Any]]
    decisionReason: Optional[PermissionDecisionReason]


class PermissionDenyDecision(TypedDict, total=False):
    behavior: Literal["deny"]
    message: str
    decisionReason: Optional[PermissionDecisionReason]


class PermissionAskDecision(TypedDict, total=False):
    behavior: Literal["ask"]
    message: str
    decisionReason: Optional[PermissionDecisionReason]
    suggestions: Optional[List[Any]]


PermissionDecision = Union[
    PermissionAllowDecision,
    PermissionDenyDecision,
    PermissionAskDecision,
]


class PermissionPassthroughResult(TypedDict, total=False):
    behavior: Literal["passthrough"]
    message: str
    updatedInput: Optional[Dict[str, Any]]
    decisionReason: Optional[PermissionDecisionReason]
    suggestions: Optional[List[Any]]


PermissionResult = Union[PermissionDecision, PermissionPassthroughResult]


# ToolPermissionContext — mirrors Tool.ToolPermissionContext
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


# Minimal Tool interface
class McpInfo(TypedDict, total=False):
    serverName: str
    toolName: Optional[str]


# ---------------------------------------------------------------------------
# Lazy imports for optional modules (feature-flagged in TS)
# ---------------------------------------------------------------------------

def _try_import_classifier_decision():
    try:
        from claude_code.utils.permissions import classifier_decision  # type: ignore[import]
        return classifier_decision
    except ImportError:
        return None


def _try_import_auto_mode_state():
    try:
        from claude_code.utils.permissions import auto_mode_state  # type: ignore[import]
        return auto_mode_state
    except ImportError:
        return None


def _try_import_denial_tracking():
    try:
        from claude_code.utils.permissions import denial_tracking  # type: ignore[import]
        return denial_tracking
    except ImportError:
        return None


def _try_import_yolo_classifier():
    try:
        from claude_code.utils.permissions import yolo_classifier  # type: ignore[import]
        return yolo_classifier
    except ImportError:
        return None


def _try_import_permissions_loader():
    try:
        from claude_code.utils.permissions import permissions_loader  # type: ignore[import]
        return permissions_loader
    except ImportError:
        return None


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


# ---------------------------------------------------------------------------
# Helper: permission_rule_parser shim
# ---------------------------------------------------------------------------

def _permission_rule_value_from_string(rule_string: str) -> PermissionRuleValueFull:
    """Parse a rule string like 'Bash(prefix:*)' into a PermissionRuleValue."""
    mod = _try_import_permission_rule_parser()
    if mod and hasattr(mod, "permission_rule_value_from_string"):
        return mod.permission_rule_value_from_string(rule_string)  # type: ignore[no-any-return]
    # Fallback: simple parser
    if "(" in rule_string and rule_string.endswith(")"):
        idx = rule_string.index("(")
        tool_name = rule_string[:idx]
        rule_content = rule_string[idx + 1 : -1]
        if rule_content == "*" or rule_content == "":
            result: PermissionRuleValueFull = {"toolName": tool_name}
        else:
            result = {"toolName": tool_name, "ruleContent": rule_content}
        return result
    return {"toolName": rule_string}


def _permission_rule_value_to_string(rule_value: PermissionRuleValueFull) -> str:
    """Serialize a PermissionRuleValue back to its canonical string form."""
    mod = _try_import_permission_rule_parser()
    if mod and hasattr(mod, "permission_rule_value_to_string"):
        return mod.permission_rule_value_to_string(rule_value)  # type: ignore[no-any-return]
    # Fallback
    tool_name = rule_value.get("toolName", "")
    rule_content = rule_value.get("ruleContent")
    if rule_content is not None:
        return f"{tool_name}({rule_content})"
    return tool_name


# ---------------------------------------------------------------------------
# Source display name
# ---------------------------------------------------------------------------

def _get_setting_source_display_name_lowercase(source: str) -> str:
    """Human-readable display for a permission rule source."""
    mapping: Dict[str, str] = {
        "policySettings": "policy settings",
        "flagSettings": "flag settings",
        "userSettings": "user settings",
        "projectSettings": "project settings",
        "localSettings": "local settings",
        "cliArg": "--allowed-tools",
        "command": "command",
        "session": "session",
    }
    return mapping.get(source, source)


def permission_rule_source_display_string(source: PermissionRuleSource) -> str:
    """Return a display string for a permission rule source."""
    return _get_setting_source_display_name_lowercase(source)


# ---------------------------------------------------------------------------
# Plural helper
# ---------------------------------------------------------------------------

def _plural(n: int, singular: str, plural_form: Optional[str] = None) -> str:
    """Return singular or plural form based on n."""
    if n == 1:
        return singular
    return plural_form if plural_form is not None else f"{singular}s"


# ---------------------------------------------------------------------------
# Rule accessors
# ---------------------------------------------------------------------------

def get_allow_rules(context: ToolPermissionContext) -> List[PermissionRule]:
    """Return all allow rules from the permission context."""
    result: List[PermissionRule] = []
    for source in PERMISSION_RULE_SOURCES:
        rule_strings = (context.get("alwaysAllowRules") or {}).get(source) or []
        for rule_string in rule_strings:
            result.append(
                {
                    "source": source,
                    "ruleBehavior": "allow",
                    "ruleValue": _permission_rule_value_from_string(rule_string),
                }
            )
    return result


def get_deny_rules(context: ToolPermissionContext) -> List[PermissionRule]:
    """Return all deny rules from the permission context."""
    result: List[PermissionRule] = []
    for source in PERMISSION_RULE_SOURCES:
        rule_strings = (context.get("alwaysDenyRules") or {}).get(source) or []
        for rule_string in rule_strings:
            result.append(
                {
                    "source": source,
                    "ruleBehavior": "deny",
                    "ruleValue": _permission_rule_value_from_string(rule_string),
                }
            )
    return result


def get_ask_rules(context: ToolPermissionContext) -> List[PermissionRule]:
    """Return all ask rules from the permission context."""
    result: List[PermissionRule] = []
    for source in PERMISSION_RULE_SOURCES:
        rule_strings = (context.get("alwaysAskRules") or {}).get(source) or []
        for rule_string in rule_strings:
            result.append(
                {
                    "source": source,
                    "ruleBehavior": "ask",
                    "ruleValue": _permission_rule_value_from_string(rule_string),
                }
            )
    return result


# ---------------------------------------------------------------------------
# MCP info helpers (mirroring mcpInfoFromString in TS)
# ---------------------------------------------------------------------------

def _mcp_info_from_string(tool_name: str) -> Optional[McpInfo]:
    """
    Parse MCP server/tool info from a tool name like 'mcp__server1__tool1'.
    Returns None if not an MCP tool name.
    """
    if not tool_name.startswith("mcp__"):
        return None
    parts = tool_name.split("__", 2)
    if len(parts) < 2:
        return None
    server_name = parts[1] if len(parts) > 1 else ""
    tool = parts[2] if len(parts) > 2 else None
    return {"serverName": server_name, "toolName": tool}


def _get_tool_name_for_permission_check(tool: Any) -> str:
    """
    Return the canonical name used for permission rule matching.
    MCP tools without prefix use their fully-qualified mcp__server__tool name.
    """
    # Try mcp_info attribute
    mcp_info = getattr(tool, "mcp_info", None) or (
        tool.get("mcpInfo") if isinstance(tool, dict) else None
    )
    if mcp_info:
        server = mcp_info.get("serverName", "")
        tool_part = mcp_info.get("toolName")
        if server:
            if tool_part:
                return f"mcp__{server}__{tool_part}"
            return f"mcp__{server}"
    name = getattr(tool, "name", None) or (tool.get("name") if isinstance(tool, dict) else "")
    return name or ""


# ---------------------------------------------------------------------------
# Rule matching
# ---------------------------------------------------------------------------

def _tool_matches_rule(
    tool: Any,
    rule: PermissionRule,
) -> bool:
    """
    Check if an entire tool matches a rule (no ruleContent in rule).
    Also matches MCP server-level rules.
    """
    rule_value = rule["ruleValue"]
    # Rule must not have content to match the entire tool
    if rule_value.get("ruleContent") is not None:
        return False

    name_for_match = _get_tool_name_for_permission_check(tool)

    # Direct tool name match
    if rule_value["toolName"] == name_for_match:
        return True

    # MCP server-level permission: "mcp__server1" matches "mcp__server1__tool1"
    # Also supports wildcard: "mcp__server1__*"
    rule_info = _mcp_info_from_string(rule_value["toolName"])
    tool_info = _mcp_info_from_string(name_for_match)

    if rule_info and tool_info:
        rule_tool = rule_info.get("toolName")
        if (rule_tool is None or rule_tool == "*") and rule_info.get("serverName") == tool_info.get("serverName"):
            return True

    return False


def tool_always_allowed_rule(
    context: ToolPermissionContext,
    tool: Any,
) -> Optional[PermissionRule]:
    """
    Check if the entire tool is listed in the always-allow rules.
    Returns the matching rule or None.
    """
    for rule in get_allow_rules(context):
        if _tool_matches_rule(tool, rule):
            return rule
    return None


def get_deny_rule_for_tool(
    context: ToolPermissionContext,
    tool: Any,
) -> Optional[PermissionRule]:
    """Check if the tool is listed in the always-deny rules."""
    for rule in get_deny_rules(context):
        if _tool_matches_rule(tool, rule):
            return rule
    return None


def get_ask_rule_for_tool(
    context: ToolPermissionContext,
    tool: Any,
) -> Optional[PermissionRule]:
    """Check if the tool is listed in the always-ask rules."""
    for rule in get_ask_rules(context):
        if _tool_matches_rule(tool, rule):
            return rule
    return None


def get_deny_rule_for_agent(
    context: ToolPermissionContext,
    agent_tool_name: str,
    agent_type: str,
) -> Optional[PermissionRule]:
    """
    Check if a specific agent is denied via Agent(agentType) syntax.
    For example, Agent(Explore) would deny the Explore agent.
    """
    for rule in get_deny_rules(context):
        rv = rule["ruleValue"]
        if rv.get("toolName") == agent_tool_name and rv.get("ruleContent") == agent_type:
            return rule
    return None


def filter_denied_agents(
    agents: List[Any],
    context: ToolPermissionContext,
    agent_tool_name: str,
) -> List[Any]:
    """
    Filter agents to exclude those that are denied via Agent(agentType) syntax.
    Parses deny rules once and collects Agent(x) contents into a set for O(rules) scan.
    """
    denied_agent_types: Set[str] = set()
    for rule in get_deny_rules(context):
        rv = rule["ruleValue"]
        if rv.get("toolName") == agent_tool_name and rv.get("ruleContent") is not None:
            denied_agent_types.add(rv["ruleContent"])  # type: ignore[typeddict-item]
    return [a for a in agents if a.get("agentType") not in denied_agent_types]


def get_rule_by_contents_for_tool(
    context: ToolPermissionContext,
    tool: Any,
    behavior: PermissionBehavior,
) -> Dict[str, PermissionRule]:
    """
    Map of rule contents to the associated rule for a given tool.
    e.g. the string key is "prefix:*" from "Bash(prefix:*)" for BashTool.
    """
    tool_name = _get_tool_name_for_permission_check(tool)
    return get_rule_by_contents_for_tool_name(context, tool_name, behavior)


def get_rule_by_contents_for_tool_name(
    context: ToolPermissionContext,
    tool_name: str,
    behavior: PermissionBehavior,
) -> Dict[str, PermissionRule]:
    """
    Used to break circular dependency where a Tool calls this function.
    Returns a map from ruleContent string → PermissionRule for the given tool.
    """
    rule_by_contents: Dict[str, PermissionRule] = {}
    if behavior == "allow":
        rules = get_allow_rules(context)
    elif behavior == "deny":
        rules = get_deny_rules(context)
    else:
        rules = get_ask_rules(context)

    for rule in rules:
        rv = rule["ruleValue"]
        rule_content = rv.get("ruleContent")
        if (
            rv.get("toolName") == tool_name
            and rule_content is not None
            and rule["ruleBehavior"] == behavior
        ):
            rule_by_contents[rule_content] = rule
    return rule_by_contents


# ---------------------------------------------------------------------------
# Permission request message builder
# ---------------------------------------------------------------------------

def create_permission_request_message(
    tool_name: str,
    decision_reason: Optional[PermissionDecisionReason] = None,
) -> str:
    """
    Creates a permission request message that explains the permission request.
    """
    if decision_reason:
        reason_type = decision_reason.get("type")  # type: ignore[union-attr]

        if reason_type == "classifier":
            classifier = decision_reason.get("classifier", "")  # type: ignore[union-attr]
            reason = decision_reason.get("reason", "")  # type: ignore[union-attr]
            return f"Classifier '{classifier}' requires approval for this {tool_name} command: {reason}"

        if reason_type == "hook":
            hook_name = decision_reason.get("hookName", "")  # type: ignore[union-attr]
            reason = decision_reason.get("reason")  # type: ignore[union-attr]
            if reason:
                return f"Hook '{hook_name}' blocked this action: {reason}"
            return f"Hook '{hook_name}' requires approval for this {tool_name} command"

        if reason_type == "rule":
            rule = decision_reason.get("rule")  # type: ignore[union-attr]
            if rule:
                rule_string = _permission_rule_value_to_string(rule["ruleValue"])
                source_string = permission_rule_source_display_string(rule["source"])
                return (
                    f"Permission rule '{rule_string}' from {source_string} "
                    f"requires approval for this {tool_name} command"
                )

        if reason_type == "subcommandResults":
            reasons = decision_reason.get("reasons", [])  # type: ignore[union-attr]
            needs_approval: List[str] = []
            for cmd, result in reasons:
                result_behavior = result.get("behavior") if isinstance(result, dict) else getattr(result, "behavior", None)
                if result_behavior in ("ask", "passthrough"):
                    if tool_name == "Bash":
                        # Strip output redirections for display
                        try:
                            from claude_code.utils.bash.commands import extract_output_redirections  # type: ignore[import]
                            cmd_without, redirections = extract_output_redirections(cmd)
                            display_cmd = cmd_without if redirections else cmd
                        except ImportError:
                            display_cmd = cmd
                        needs_approval.append(display_cmd)
                    else:
                        needs_approval.append(cmd)
            if needs_approval:
                n = len(needs_approval)
                parts_word = _plural(n, "part")
                requires_word = _plural(n, "requires", "require")
                return (
                    f"This {tool_name} command contains multiple operations. "
                    f"The following {parts_word} {requires_word} approval: {', '.join(needs_approval)}"
                )
            return f"This {tool_name} command contains multiple operations that require approval"

        if reason_type == "permissionPromptTool":
            prompt_tool_name = decision_reason.get("permissionPromptToolName", "")  # type: ignore[union-attr]
            return f"Tool '{prompt_tool_name}' requires approval for this {tool_name} command"

        if reason_type == "sandboxOverride":
            return "Run outside of the sandbox"

        if reason_type == "workingDir":
            return decision_reason.get("reason", "")  # type: ignore[union-attr]

        if reason_type in ("safetyCheck", "other"):
            return decision_reason.get("reason", "")  # type: ignore[union-attr]

        if reason_type == "mode":
            mode = decision_reason.get("mode", "")  # type: ignore[union-attr]
            try:
                from claude_code.utils.permissions.permission_mode import permission_mode_title  # type: ignore[import]
                mode_title = permission_mode_title(mode)
            except ImportError:
                mode_title = mode
            return (
                f"Current permission mode ({mode_title}) requires approval for this {tool_name} command"
            )

        if reason_type == "asyncAgent":
            return decision_reason.get("reason", "")  # type: ignore[union-attr]

    # Default message
    return f"Claude requested permissions to use {tool_name}, but you haven't granted it yet."


# ---------------------------------------------------------------------------
# Denial-state helpers (wraps denial_tracking module)
# ---------------------------------------------------------------------------

def _create_denial_tracking_state() -> Any:
    mod = _try_import_denial_tracking()
    if mod and hasattr(mod, "create_denial_tracking_state"):
        return mod.create_denial_tracking_state()
    return {"consecutiveDenials": 0, "totalDenials": 0}


def _record_denial(state: Any) -> Any:
    mod = _try_import_denial_tracking()
    if mod and hasattr(mod, "record_denial"):
        return mod.record_denial(state)
    if isinstance(state, dict):
        return {
            **state,
            "consecutiveDenials": state.get("consecutiveDenials", 0) + 1,
            "totalDenials": state.get("totalDenials", 0) + 1,
        }
    return state


def _record_success(state: Any) -> Any:
    mod = _try_import_denial_tracking()
    if mod and hasattr(mod, "record_success"):
        return mod.record_success(state)
    if isinstance(state, dict):
        if state.get("consecutiveDenials", 0) == 0:
            return state
        return {**state, "consecutiveDenials": 0}
    return state


def _should_fallback_to_prompting(state: Any) -> bool:
    mod = _try_import_denial_tracking()
    if mod and hasattr(mod, "should_fallback_to_prompting"):
        return mod.should_fallback_to_prompting(state)
    return False


def _get_denial_limits() -> Any:
    mod = _try_import_denial_tracking()
    if mod and hasattr(mod, "DENIAL_LIMITS"):
        return mod.DENIAL_LIMITS
    return {"maxConsecutive": 3, "maxTotal": 10}


# ---------------------------------------------------------------------------
# Headless agent hook runner (async)
# ---------------------------------------------------------------------------

async def _run_permission_request_hooks_for_headless_agent(
    tool: Any,
    input_data: Dict[str, Any],
    tool_use_id: str,
    context: Any,
    permission_mode: Optional[str],
    suggestions: Optional[List[Any]],
) -> Optional[PermissionDecision]:
    """
    Runs PermissionRequest hooks for headless/async agents that cannot show
    permission prompts. Gives hooks an opportunity to allow or deny tool use
    before the fallback auto-deny kicks in.

    Returns a PermissionDecision if a hook made a decision, or None if no
    hook provided a decision (caller should proceed to auto-deny).
    """
    try:
        from claude_code.utils.hooks import execute_permission_request_hooks  # type: ignore[import]
        from claude_code.utils.permissions.permission_update import (  # type: ignore[import]
            apply_permission_updates,
            persist_permission_updates,
        )

        async def _iterate_hooks() -> Optional[PermissionDecision]:
            signal = getattr(getattr(context, "abort_controller", None), "signal", None)
            async for hook_result in execute_permission_request_hooks(
                tool.name,
                tool_use_id,
                input_data,
                context,
                permission_mode,
                suggestions,
                signal,
            ):
                if not hook_result.permission_request_result:
                    continue
                decision = hook_result.permission_request_result
                if decision.get("behavior") == "allow":
                    final_input = decision.get("updatedInput") or input_data
                    updated_permissions = decision.get("updatedPermissions")
                    if updated_permissions:
                        persist_permission_updates(updated_permissions)
                        prev = context.get_app_state()
                        context.set_app_state(
                            lambda prev_state, _up=updated_permissions: {
                                **prev_state,
                                "toolPermissionContext": apply_permission_updates(
                                    prev_state["toolPermissionContext"], _up
                                ),
                            }
                        )
                    return {
                        "behavior": "allow",
                        "updatedInput": final_input,
                        "decisionReason": {
                            "type": "hook",
                            "hookName": "PermissionRequest",
                        },
                    }
                if decision.get("behavior") == "deny":
                    if decision.get("interrupt"):
                        logger.debug(
                            "Hook interrupt: tool=%s hookMessage=%s",
                            tool.name,
                            decision.get("message"),
                        )
                        abort_controller = getattr(context, "abort_controller", None)
                        if abort_controller:
                            abort_controller.abort()
                    return {
                        "behavior": "deny",
                        "message": decision.get("message") or "Permission denied by hook",
                        "decisionReason": {
                            "type": "hook",
                            "hookName": "PermissionRequest",
                            "reason": decision.get("message"),
                        },
                    }
            return None

        return await _iterate_hooks()

    except Exception as e:
        # If hooks fail, fall through to auto-deny rather than crashing
        logger.error("PermissionRequest hook failed for headless agent: %s", e)
        return None


# ---------------------------------------------------------------------------
# Persist denial state
# ---------------------------------------------------------------------------

def _persist_denial_state(context: Any, new_state: Any) -> None:
    """
    Persist denial tracking state. For async subagents with local_denial_tracking,
    mutate the local state in place. Otherwise, write to app_state.
    """
    local = getattr(context, "local_denial_tracking", None)
    if local is not None:
        if isinstance(local, dict) and isinstance(new_state, dict):
            local.update(new_state)
        elif hasattr(local, "__dict__") and hasattr(new_state, "__dict__"):
            local.__dict__.update(new_state.__dict__)
    else:
        def _updater(prev: Dict[str, Any]) -> Dict[str, Any]:
            if prev.get("denialTracking") is new_state:
                return prev
            return {**prev, "denialTracking": new_state}
        if hasattr(context, "set_app_state"):
            context.set_app_state(_updater)


# ---------------------------------------------------------------------------
# Denial limit handler
# ---------------------------------------------------------------------------

def _handle_denial_limit_exceeded(
    denial_state: Any,
    app_state: Any,
    classifier_reason: str,
    assistant_message: Any,
    tool: Any,
    result: PermissionDecision,
    context: Any,
) -> Optional[PermissionDecision]:
    """
    Check if a denial limit was exceeded and return an 'ask' result
    so the user can review. Returns None if no limit was hit.
    """
    if not _should_fallback_to_prompting(denial_state):
        return None

    denial_limits = _get_denial_limits()
    max_total = denial_limits.get("maxTotal", 10) if isinstance(denial_limits, dict) else getattr(denial_limits, "maxTotal", 10)
    total_denials = denial_state.get("totalDenials", 0) if isinstance(denial_state, dict) else getattr(denial_state, "totalDenials", 0)
    consecutive_denials = denial_state.get("consecutiveDenials", 0) if isinstance(denial_state, dict) else getattr(denial_state, "consecutiveDenials", 0)

    hit_total_limit = total_denials >= max_total
    tool_permission_context = (
        app_state.get("toolPermissionContext", {})
        if isinstance(app_state, dict)
        else getattr(app_state, "toolPermissionContext", {})
    )
    is_headless = (
        tool_permission_context.get("shouldAvoidPermissionPrompts", False)
        if isinstance(tool_permission_context, dict)
        else getattr(tool_permission_context, "shouldAvoidPermissionPrompts", False)
    )

    total_count = total_denials
    consecutive_count = consecutive_denials

    if hit_total_limit:
        warning = f"{total_count} actions were blocked this session. Please review the transcript before continuing."
    else:
        warning = f"{consecutive_count} consecutive actions were blocked. Please review the transcript before continuing."

    if is_headless:
        raise RuntimeError("Agent aborted: too many classifier denials in headless mode")

    logger.debug("Classifier denial limit exceeded, falling back to prompting: %s", warning)

    if hit_total_limit:
        if isinstance(denial_state, dict):
            reset_state = {**denial_state, "totalDenials": 0, "consecutiveDenials": 0}
        else:
            reset_state = denial_state
        _persist_denial_state(context, reset_state)

    # Preserve the original classifier value
    result_reason = result.get("decisionReason")  # type: ignore[union-attr]
    if result_reason and result_reason.get("type") == "classifier":  # type: ignore[union-attr]
        original_classifier = result_reason.get("classifier", "auto-mode")  # type: ignore[union-attr]
    else:
        original_classifier = "auto-mode"

    return {
        **result,  # type: ignore[misc]
        "decisionReason": {
            "type": "classifier",
            "classifier": original_classifier,
            "reason": f"{warning}\n\nLatest blocked action: {classifier_reason}",
        },
    }


# ---------------------------------------------------------------------------
# Rule-based permission check (subset used by bypassPermissions)
# ---------------------------------------------------------------------------

async def check_rule_based_permissions(
    tool: Any,
    input_data: Dict[str, Any],
    context: Any,
) -> Optional[Union[PermissionAskDecision, PermissionDenyDecision]]:
    """
    Check only the rule-based steps of the permission pipeline — the subset
    that bypassPermissions mode respects (everything that fires before step 2a).

    Returns a deny/ask decision if a rule blocks the tool, or None if no rule
    objects.
    """
    app_state = context.get_app_state() if hasattr(context, "get_app_state") else {}
    permission_ctx = (
        app_state.get("toolPermissionContext", {})
        if isinstance(app_state, dict)
        else getattr(app_state, "toolPermissionContext", {})
    )

    BASH_TOOL_NAME = _get_bash_tool_name()

    # 1a. Entire tool is denied by rule
    deny_rule = get_deny_rule_for_tool(permission_ctx, tool)
    if deny_rule:
        tool_name = _get_tool_name_from_obj(tool)
        return {
            "behavior": "deny",
            "decisionReason": {"type": "rule", "rule": deny_rule},
            "message": f"Permission to use {tool_name} has been denied.",
        }

    # 1b. Entire tool has an ask rule
    ask_rule = get_ask_rule_for_tool(permission_ctx, tool)
    if ask_rule:
        can_sandbox_auto_allow = _check_sandbox_auto_allow(tool, input_data, BASH_TOOL_NAME)
        if not can_sandbox_auto_allow:
            tool_name = _get_tool_name_from_obj(tool)
            return {
                "behavior": "ask",
                "decisionReason": {"type": "rule", "rule": ask_rule},
                "message": create_permission_request_message(tool_name),
            }
        # Fall through to let tool.checkPermissions handle command-specific rules

    # 1c. Tool-specific permission check
    tool_name = _get_tool_name_from_obj(tool)
    tool_permission_result: PermissionResult = {
        "behavior": "passthrough",
        "message": create_permission_request_message(tool_name),
    }
    try:
        if hasattr(tool, "check_permissions"):
            parsed_input = _parse_tool_input(tool, input_data)
            tool_permission_result = await tool.check_permissions(parsed_input, context)
    except Exception as e:
        if _is_abort_error(e):
            raise
        logger.error("Error in tool.check_permissions: %s", e)

    # 1d. Tool implementation denied
    if tool_permission_result.get("behavior") == "deny":
        return tool_permission_result  # type: ignore[return-value]

    # 1f. Content-specific ask rules from tool.checkPermissions
    if (
        tool_permission_result.get("behavior") == "ask"
        and (tool_permission_result.get("decisionReason") or {}).get("type") == "rule"
        and (tool_permission_result.get("decisionReason") or {}).get("rule", {}).get("ruleBehavior") == "ask"
    ):
        return tool_permission_result  # type: ignore[return-value]

    # 1g. Safety checks are bypass-immune
    if (
        tool_permission_result.get("behavior") == "ask"
        and (tool_permission_result.get("decisionReason") or {}).get("type") == "safetyCheck"
    ):
        return tool_permission_result  # type: ignore[return-value]

    # No rule-based objection
    return None


# ---------------------------------------------------------------------------
# Inner permission check
# ---------------------------------------------------------------------------

async def _has_permissions_to_use_tool_inner(
    tool: Any,
    input_data: Dict[str, Any],
    context: Any,
) -> PermissionDecision:
    """
    Core permission pipeline: rule checks → bypass → allow-rules → ask.
    """
    abort_controller = getattr(context, "abort_controller", None)
    abort_signal = getattr(abort_controller, "signal", None)
    if abort_signal and getattr(abort_signal, "aborted", False):
        raise _make_abort_error()

    app_state = context.get_app_state() if hasattr(context, "get_app_state") else {}
    permission_ctx = (
        app_state.get("toolPermissionContext", {})
        if isinstance(app_state, dict)
        else getattr(app_state, "toolPermissionContext", {})
    )

    BASH_TOOL_NAME = _get_bash_tool_name()
    tool_name = _get_tool_name_from_obj(tool)

    # 1a. Entire tool is denied
    deny_rule = get_deny_rule_for_tool(permission_ctx, tool)
    if deny_rule:
        return {
            "behavior": "deny",
            "decisionReason": {"type": "rule", "rule": deny_rule},
            "message": f"Permission to use {tool_name} has been denied.",
        }

    # 1b. Entire tool has an ask rule
    ask_rule = get_ask_rule_for_tool(permission_ctx, tool)
    if ask_rule:
        can_sandbox_auto_allow = _check_sandbox_auto_allow(tool, input_data, BASH_TOOL_NAME)
        if not can_sandbox_auto_allow:
            return {
                "behavior": "ask",
                "decisionReason": {"type": "rule", "rule": ask_rule},
                "message": create_permission_request_message(tool_name),
            }
        # Fall through to let Bash's checkPermissions handle command-specific rules

    # 1c. Ask the tool implementation for a permission result
    tool_permission_result: PermissionResult = {
        "behavior": "passthrough",
        "message": create_permission_request_message(tool_name),
    }
    try:
        if hasattr(tool, "check_permissions"):
            parsed_input = _parse_tool_input(tool, input_data)
            tool_permission_result = await tool.check_permissions(parsed_input, context)
    except Exception as e:
        if _is_abort_error(e):
            raise
        logger.error("Error in tool.check_permissions: %s", e)

    # 1d. Tool implementation denied permission
    if tool_permission_result.get("behavior") == "deny":
        return tool_permission_result  # type: ignore[return-value]

    # 1e. Tool requires user interaction even in bypass mode
    if (
        hasattr(tool, "requires_user_interaction")
        and tool.requires_user_interaction()
        and tool_permission_result.get("behavior") == "ask"
    ):
        return tool_permission_result  # type: ignore[return-value]

    # 1f. Content-specific ask rules take precedence over bypassPermissions mode
    if (
        tool_permission_result.get("behavior") == "ask"
        and (tool_permission_result.get("decisionReason") or {}).get("type") == "rule"
        and (tool_permission_result.get("decisionReason") or {}).get("rule", {}).get("ruleBehavior") == "ask"
    ):
        return tool_permission_result  # type: ignore[return-value]

    # 1g. Safety checks are bypass-immune
    if (
        tool_permission_result.get("behavior") == "ask"
        and (tool_permission_result.get("decisionReason") or {}).get("type") == "safetyCheck"
    ):
        return tool_permission_result  # type: ignore[return-value]

    # 2a. Check if mode allows the tool to run
    # Re-read app_state for latest value
    app_state = context.get_app_state() if hasattr(context, "get_app_state") else {}
    permission_ctx = (
        app_state.get("toolPermissionContext", {})
        if isinstance(app_state, dict)
        else getattr(app_state, "toolPermissionContext", {})
    )
    mode = (
        permission_ctx.get("mode", "default")
        if isinstance(permission_ctx, dict)
        else getattr(permission_ctx, "mode", "default")
    )
    is_bypass_perm_available = (
        permission_ctx.get("isBypassPermissionsModeAvailable", False)
        if isinstance(permission_ctx, dict)
        else getattr(permission_ctx, "isBypassPermissionsModeAvailable", False)
    )

    should_bypass = mode == "bypassPermissions" or (
        mode == "plan" and is_bypass_perm_available
    )
    if should_bypass:
        return {
            "behavior": "allow",
            "updatedInput": _get_updated_input_or_fallback(tool_permission_result, input_data),
            "decisionReason": {"type": "mode", "mode": mode},
        }

    # 2b. Entire tool is always allowed
    always_allowed_rule = tool_always_allowed_rule(permission_ctx, tool)
    if always_allowed_rule:
        return {
            "behavior": "allow",
            "updatedInput": _get_updated_input_or_fallback(tool_permission_result, input_data),
            "decisionReason": {"type": "rule", "rule": always_allowed_rule},
        }

    # 3. Convert "passthrough" to "ask"
    if tool_permission_result.get("behavior") == "passthrough":
        result: PermissionDecision = {
            **tool_permission_result,  # type: ignore[misc]
            "behavior": "ask",
            "message": create_permission_request_message(
                tool_name, tool_permission_result.get("decisionReason")  # type: ignore[arg-type]
            ),
        }
    else:
        result = tool_permission_result  # type: ignore[assignment]

    if result.get("behavior") == "ask" and result.get("suggestions"):  # type: ignore[union-attr]
        logger.debug("Permission suggestions for %s: %s", tool_name, result.get("suggestions"))  # type: ignore[union-attr]

    return result


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------

async def has_permissions_to_use_tool(
    tool: Any,
    input_data: Dict[str, Any],
    context: Any,
    assistant_message: Any = None,
    tool_use_id: str = "",
) -> PermissionDecision:
    """
    Main permission check function. Returns a PermissionDecision.

    Mirrors hasPermissionsToUseTool from permissions.ts.
    """
    result = await _has_permissions_to_use_tool_inner(tool, input_data, context)

    app_state = context.get_app_state() if hasattr(context, "get_app_state") else {}
    permission_ctx = (
        app_state.get("toolPermissionContext", {})
        if isinstance(app_state, dict)
        else getattr(app_state, "toolPermissionContext", {})
    )

    # Reset consecutive denials on any allowed tool use in auto mode
    if result.get("behavior") == "allow":
        mode = (
            permission_ctx.get("mode", "default")
            if isinstance(permission_ctx, dict)
            else getattr(permission_ctx, "mode", "default")
        )
        local_denial = getattr(context, "local_denial_tracking", None)
        denial_state = local_denial or (
            app_state.get("denialTracking") if isinstance(app_state, dict) else getattr(app_state, "denialTracking", None)
        )
        if (
            mode == "auto"
            and denial_state
            and (denial_state.get("consecutiveDenials", 0) if isinstance(denial_state, dict) else getattr(denial_state, "consecutiveDenials", 0)) > 0
        ):
            new_denial_state = _record_success(denial_state)
            _persist_denial_state(context, new_denial_state)
        return result

    # Apply dontAsk mode transformation: convert 'ask' to 'deny'
    if result.get("behavior") == "ask":
        mode = (
            permission_ctx.get("mode", "default")
            if isinstance(permission_ctx, dict)
            else getattr(permission_ctx, "mode", "default")
        )
        tool_name = _get_tool_name_from_obj(tool)

        if mode == "dontAsk":
            dont_ask_msg = _build_dont_ask_reject_message(tool_name)
            return {
                "behavior": "deny",
                "decisionReason": {"type": "mode", "mode": "dontAsk"},
                "message": dont_ask_msg,
            }

        # Auto mode: use AI classifier instead of prompting user
        auto_mode_state_mod = _try_import_auto_mode_state()
        is_auto_mode_active = (
            auto_mode_state_mod.is_auto_mode_active()
            if auto_mode_state_mod and hasattr(auto_mode_state_mod, "is_auto_mode_active")
            else False
        )
        if mode == "auto" or (mode == "plan" and is_auto_mode_active):
            # Non-classifier-approvable safetyCheck decisions stay immune
            result_reason = result.get("decisionReason")  # type: ignore[union-attr]
            if (
                result_reason
                and result_reason.get("type") == "safetyCheck"  # type: ignore[union-attr]
                and not result_reason.get("classifierApprovable", False)  # type: ignore[union-attr]
            ):
                should_avoid = (
                    permission_ctx.get("shouldAvoidPermissionPrompts", False)
                    if isinstance(permission_ctx, dict)
                    else getattr(permission_ctx, "shouldAvoidPermissionPrompts", False)
                )
                if should_avoid:
                    return {
                        "behavior": "deny",
                        "message": result.get("message", ""),  # type: ignore[union-attr]
                        "decisionReason": {
                            "type": "asyncAgent",
                            "reason": "Safety check requires interactive approval and permission prompts are not available in this context",
                        },
                    }
                return result

            if hasattr(tool, "requires_user_interaction") and tool.requires_user_interaction() and result.get("behavior") == "ask":
                return result

            # Denial tracking state
            local_denial = getattr(context, "local_denial_tracking", None)
            denial_state = local_denial or (
                app_state.get("denialTracking") if isinstance(app_state, dict) else getattr(app_state, "denialTracking", None)
            ) or _create_denial_tracking_state()

            POWERSHELL_TOOL_NAME = _get_powershell_tool_name()

            # PowerShell requires explicit user permission in auto mode
            if tool_name == POWERSHELL_TOOL_NAME and not _feature_powershell_auto_mode():
                should_avoid = (
                    permission_ctx.get("shouldAvoidPermissionPrompts", False)
                    if isinstance(permission_ctx, dict)
                    else getattr(permission_ctx, "shouldAvoidPermissionPrompts", False)
                )
                if should_avoid:
                    return {
                        "behavior": "deny",
                        "message": "PowerShell tool requires interactive approval",
                        "decisionReason": {
                            "type": "asyncAgent",
                            "reason": "PowerShell tool requires interactive approval and permission prompts are not available in this context",
                        },
                    }
                logger.debug("Skipping auto mode classifier for %s: tool requires explicit user permission", tool_name)
                return result

            # acceptEdits fast-path (skip for Agent and REPL)
            AGENT_TOOL_NAME = _get_agent_tool_name()
            REPL_TOOL_NAME = _get_repl_tool_name()
            if result.get("behavior") == "ask" and tool_name not in (AGENT_TOOL_NAME, REPL_TOOL_NAME):
                try:
                    accept_edits_result = await _check_accept_edits(tool, input_data, context)
                    if accept_edits_result and accept_edits_result.get("behavior") == "allow":
                        new_denial_state = _record_success(denial_state)
                        _persist_denial_state(context, new_denial_state)
                        logger.debug("Skipping auto mode classifier for %s: would be allowed in acceptEdits mode", tool_name)
                        return {
                            "behavior": "allow",
                            "updatedInput": accept_edits_result.get("updatedInput") or input_data,
                            "decisionReason": {"type": "mode", "mode": "auto"},
                        }
                except Exception as e:
                    if _is_abort_error(e):
                        raise
                    # If the acceptEdits check fails, fall through to the classifier

            # Allowlisted tools fast-path
            classifier_decision_mod = _try_import_classifier_decision()
            if (
                classifier_decision_mod
                and hasattr(classifier_decision_mod, "is_auto_mode_allowlisted_tool")
                and classifier_decision_mod.is_auto_mode_allowlisted_tool(tool_name)
            ):
                new_denial_state = _record_success(denial_state)
                _persist_denial_state(context, new_denial_state)
                logger.debug("Skipping auto mode classifier for %s: tool is on the safe allowlist", tool_name)
                return {
                    "behavior": "allow",
                    "updatedInput": input_data,
                    "decisionReason": {"type": "mode", "mode": "auto"},
                }

            # Run the auto mode classifier
            yolo_mod = _try_import_yolo_classifier()
            if yolo_mod and hasattr(yolo_mod, "format_action_for_classifier") and hasattr(yolo_mod, "classify_yolo_action"):
                action = yolo_mod.format_action_for_classifier(tool_name, input_data)
                try:
                    from claude_code.utils.classifier_approvals import set_classifier_checking, clear_classifier_checking  # type: ignore[import]
                    set_classifier_checking(tool_use_id)
                except ImportError:
                    pass

                classifier_result = None
                try:
                    messages = getattr(context, "messages", [])
                    options = getattr(context, "options", {})
                    tools = options.get("tools", []) if isinstance(options, dict) else getattr(options, "tools", [])
                    abort_signal = getattr(getattr(context, "abort_controller", None), "signal", None)
                    classifier_result = await yolo_mod.classify_yolo_action(
                        messages, action, tools, permission_ctx, abort_signal
                    )
                finally:
                    try:
                        from claude_code.utils.classifier_approvals import clear_classifier_checking  # type: ignore[import]
                        clear_classifier_checking(tool_use_id)
                    except ImportError:
                        pass

                if classifier_result:
                    if classifier_result.get("shouldBlock"):
                        # Transcript too long — fall back to normal prompting
                        if classifier_result.get("transcriptTooLong"):
                            should_avoid = (
                                permission_ctx.get("shouldAvoidPermissionPrompts", False)
                                if isinstance(permission_ctx, dict)
                                else getattr(permission_ctx, "shouldAvoidPermissionPrompts", False)
                            )
                            if should_avoid:
                                raise RuntimeError(
                                    "Agent aborted: auto mode classifier transcript exceeded context window in headless mode"
                                )
                            logger.warning("Auto mode classifier transcript too long, falling back to normal permission handling")
                            return {
                                **result,  # type: ignore[misc]
                                "decisionReason": {
                                    "type": "other",
                                    "reason": "Auto mode classifier transcript exceeded context window — falling back to manual approval",
                                },
                            }

                        # Classifier unavailable
                        if classifier_result.get("unavailable"):
                            logger.warning("Auto mode classifier unavailable, denying (fail closed)")
                            return {
                                "behavior": "deny",
                                "decisionReason": {
                                    "type": "classifier",
                                    "classifier": "auto-mode",
                                    "reason": "Classifier unavailable",
                                },
                                "message": _build_classifier_unavailable_message(tool_name, classifier_result.get("model")),
                            }

                        # Update denial tracking and check limits
                        new_denial_state = _record_denial(denial_state)
                        _persist_denial_state(context, new_denial_state)
                        logger.debug("Auto mode classifier blocked action: %s", classifier_result.get("reason"))

                        denial_limit_result = _handle_denial_limit_exceeded(
                            new_denial_state, app_state, classifier_result.get("reason", ""),
                            assistant_message, tool, result, context
                        )
                        if denial_limit_result:
                            return denial_limit_result

                        return {
                            "behavior": "deny",
                            "decisionReason": {
                                "type": "classifier",
                                "classifier": "auto-mode",
                                "reason": classifier_result.get("reason", ""),
                            },
                            "message": _build_yolo_rejection_message(classifier_result.get("reason", "")),
                        }

                    # Classifier allowed
                    new_denial_state = _record_success(denial_state)
                    _persist_denial_state(context, new_denial_state)
                    return {
                        "behavior": "allow",
                        "updatedInput": input_data,
                        "decisionReason": {
                            "type": "classifier",
                            "classifier": "auto-mode",
                            "reason": classifier_result.get("reason", ""),
                        },
                    }

        # When permission prompts should be avoided, run PermissionRequest hooks first
        should_avoid = (
            permission_ctx.get("shouldAvoidPermissionPrompts", False)
            if isinstance(permission_ctx, dict)
            else getattr(permission_ctx, "shouldAvoidPermissionPrompts", False)
        )
        if should_avoid:
            hook_decision = await _run_permission_request_hooks_for_headless_agent(
                tool, input_data, tool_use_id, context,
                (
                    permission_ctx.get("mode")
                    if isinstance(permission_ctx, dict)
                    else getattr(permission_ctx, "mode", None)
                ),
                result.get("suggestions"),  # type: ignore[union-attr]
            )
            if hook_decision:
                return hook_decision
            tool_name = _get_tool_name_from_obj(tool)
            return {
                "behavior": "deny",
                "decisionReason": {
                    "type": "asyncAgent",
                    "reason": "Permission prompts are not available in this context",
                },
                "message": _build_auto_reject_message(tool_name),
            }

    return result


# ---------------------------------------------------------------------------
# Permission rule CRUD
# ---------------------------------------------------------------------------

async def delete_permission_rule(
    rule: PermissionRule,
    initial_context: ToolPermissionContext,
    set_tool_permission_context: Any,  # callable
) -> None:
    """Delete a permission rule from the appropriate destination."""
    if rule["source"] in ("policySettings", "flagSettings", "command"):
        raise ValueError("Cannot delete permission rules from read-only settings")

    pu_mod = _try_import_permission_update()
    pl_mod = _try_import_permissions_loader()

    if pu_mod and hasattr(pu_mod, "apply_permission_update"):
        updated_context = pu_mod.apply_permission_update(
            initial_context,
            {
                "type": "removeRules",
                "rules": [rule["ruleValue"]],
                "behavior": rule["ruleBehavior"],
                "destination": rule["source"],
            },
        )
    else:
        updated_context = initial_context

    destination = rule["source"]
    if destination in ("localSettings", "userSettings", "projectSettings"):
        if pl_mod and hasattr(pl_mod, "delete_permission_rule_from_settings"):
            pl_mod.delete_permission_rule_from_settings(rule)
    # cliArg, session: no action needed — not persisted to disk

    set_tool_permission_context(updated_context)


def _convert_rules_to_updates(
    rules: List[PermissionRule],
    update_type: Literal["addRules", "replaceRules"],
) -> List[Any]:
    """
    Helper to convert PermissionRule array to PermissionUpdate array.
    Groups rules by source and behavior.
    """
    grouped: Dict[str, List[PermissionRuleValueFull]] = {}
    for rule in rules:
        key = f"{rule['source']}:{rule['ruleBehavior']}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(rule["ruleValue"])

    updates: List[Any] = []
    for key, rule_values in grouped.items():
        source, behavior = key.split(":", 1)
        updates.append({
            "type": update_type,
            "rules": rule_values,
            "behavior": behavior,
            "destination": source,
        })
    return updates


def apply_permission_rules_to_permission_context(
    tool_permission_context: ToolPermissionContext,
    rules: List[PermissionRule],
) -> ToolPermissionContext:
    """Apply permission rules to context (additive - for initial setup)."""
    pu_mod = _try_import_permission_update()
    updates = _convert_rules_to_updates(rules, "addRules")
    if pu_mod and hasattr(pu_mod, "apply_permission_updates"):
        return pu_mod.apply_permission_updates(tool_permission_context, updates)
    # Fallback: return unchanged
    return tool_permission_context


def sync_permission_rules_from_disk(
    tool_permission_context: ToolPermissionContext,
    rules: List[PermissionRule],
) -> ToolPermissionContext:
    """Sync permission rules from disk (replacement - for settings changes)."""
    pu_mod = _try_import_permission_update()
    pl_mod = _try_import_permissions_loader()

    context = tool_permission_context

    # When allowManagedPermissionRulesOnly is enabled, clear all non-policy sources
    should_restrict = False
    if pl_mod and hasattr(pl_mod, "should_allow_managed_permission_rules_only"):
        should_restrict = pl_mod.should_allow_managed_permission_rules_only()

    if should_restrict and pu_mod and hasattr(pu_mod, "apply_permission_update"):
        sources_to_clear = ["userSettings", "projectSettings", "localSettings", "cliArg", "session"]
        behaviors: List[PermissionBehavior] = ["allow", "deny", "ask"]
        for source in sources_to_clear:
            for behavior in behaviors:
                context = pu_mod.apply_permission_update(context, {
                    "type": "replaceRules",
                    "rules": [],
                    "behavior": behavior,
                    "destination": source,
                })

    # Clear all disk-based source:behavior combos before applying new rules
    disk_sources = ["userSettings", "projectSettings", "localSettings"]
    if pu_mod and hasattr(pu_mod, "apply_permission_update"):
        for disk_source in disk_sources:
            for behavior in ["allow", "deny", "ask"]:
                context = pu_mod.apply_permission_update(context, {
                    "type": "replaceRules",
                    "rules": [],
                    "behavior": behavior,
                    "destination": disk_source,
                })

    updates = _convert_rules_to_updates(rules, "replaceRules")
    if pu_mod and hasattr(pu_mod, "apply_permission_updates"):
        return pu_mod.apply_permission_updates(context, updates)
    return context


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _get_updated_input_or_fallback(
    permission_result: PermissionResult,
    fallback: Dict[str, Any],
) -> Dict[str, Any]:
    """Extract updatedInput from a permission result, falling back to the original input."""
    if isinstance(permission_result, dict):
        return permission_result.get("updatedInput") or fallback
    return fallback


def _get_tool_name_from_obj(tool: Any) -> str:
    """Get tool name from a tool object or dict."""
    if isinstance(tool, dict):
        return tool.get("name", "")
    return getattr(tool, "name", "")


def _get_bash_tool_name() -> str:
    try:
        from claude_code.constants.tools import BASH_TOOL_NAME  # type: ignore[import]
        return BASH_TOOL_NAME
    except ImportError:
        return "Bash"


def _get_powershell_tool_name() -> str:
    try:
        from claude_code.constants.tools import POWERSHELL_TOOL_NAME  # type: ignore[import]
        return POWERSHELL_TOOL_NAME
    except ImportError:
        return "PowerShell"


def _get_agent_tool_name() -> str:
    try:
        from claude_code.tools.agent_tool.constants import AGENT_TOOL_NAME  # type: ignore[import]
        return AGENT_TOOL_NAME
    except ImportError:
        return "Agent"


def _get_repl_tool_name() -> str:
    try:
        from claude_code.tools.repl_tool.constants import REPL_TOOL_NAME  # type: ignore[import]
        return REPL_TOOL_NAME
    except ImportError:
        return "REPL"


def _check_sandbox_auto_allow(tool: Any, input_data: Dict[str, Any], bash_tool_name: str) -> bool:
    """Check if sandbox auto-allow applies."""
    try:
        from claude_code.utils.sandbox.sandbox_adapter import SandboxManager  # type: ignore[import]
        from claude_code.tools.bash_tool.should_use_sandbox import should_use_sandbox  # type: ignore[import]
        tool_name = _get_tool_name_from_obj(tool)
        return (
            tool_name == bash_tool_name
            and SandboxManager.is_sandboxing_enabled()
            and SandboxManager.is_auto_allow_bash_if_sandboxed_enabled()
            and should_use_sandbox(input_data)
        )
    except ImportError:
        return False


def _parse_tool_input(tool: Any, input_data: Dict[str, Any]) -> Any:
    """Parse and validate tool input using the tool's input schema."""
    schema = getattr(tool, "input_schema", None)
    if schema and hasattr(schema, "parse"):
        return schema.parse(input_data)
    return input_data


def _is_abort_error(e: Exception) -> bool:
    """Check if an exception is an abort/user-abort error."""
    type_name = type(e).__name__
    return type_name in ("AbortError", "APIUserAbortError") or "abort" in type_name.lower()


def _make_abort_error() -> Exception:
    """Create an AbortError."""
    try:
        from claude_code.utils.errors import AbortError  # type: ignore[import]
        return AbortError()
    except ImportError:
        return RuntimeError("AbortError")


def _feature_powershell_auto_mode() -> bool:
    """Check if POWERSHELL_AUTO_MODE feature is enabled."""
    try:
        from claude_code.utils.feature import feature  # type: ignore[import]
        return feature("POWERSHELL_AUTO_MODE")
    except ImportError:
        return False


async def _check_accept_edits(
    tool: Any,
    input_data: Dict[str, Any],
    context: Any,
) -> Optional[PermissionResult]:
    """Run tool.check_permissions in acceptEdits mode."""
    if not hasattr(tool, "check_permissions"):
        return None
    try:
        parsed_input = _parse_tool_input(tool, input_data)

        class _AcceptEditsContext:
            def __init__(self, ctx: Any) -> None:
                self._ctx = ctx

            def get_app_state(self) -> Any:
                state = self._ctx.get_app_state()
                if isinstance(state, dict):
                    perm_ctx = state.get("toolPermissionContext", {})
                    return {
                        **state,
                        "toolPermissionContext": {
                            **perm_ctx,
                            "mode": "acceptEdits",
                        },
                    }
                return state

            def __getattr__(self, name: str) -> Any:
                return getattr(self._ctx, name)

        return await tool.check_permissions(parsed_input, _AcceptEditsContext(context))
    except Exception as e:
        if _is_abort_error(e):
            raise
        return None


def _build_dont_ask_reject_message(tool_name: str) -> str:
    """Build rejection message for dontAsk mode."""
    try:
        from claude_code.utils.messages import DONT_ASK_REJECT_MESSAGE  # type: ignore[import]
        return DONT_ASK_REJECT_MESSAGE(tool_name)
    except ImportError:
        return f"Skipped permission request for {tool_name} (dontAsk mode)"


def _build_auto_reject_message(tool_name: str) -> str:
    """Build rejection message for headless/auto agent."""
    try:
        from claude_code.utils.messages import AUTO_REJECT_MESSAGE  # type: ignore[import]
        return AUTO_REJECT_MESSAGE(tool_name)
    except ImportError:
        return f"Permission request for {tool_name} auto-rejected (headless mode)"


def _build_classifier_unavailable_message(tool_name: str, model: Optional[str]) -> str:
    """Build message when classifier is unavailable."""
    try:
        from claude_code.utils.messages import build_classifier_unavailable_message  # type: ignore[import]
        return build_classifier_unavailable_message(tool_name, model)
    except ImportError:
        return f"Auto mode classifier is unavailable. Please retry or manually approve {tool_name}."


def _build_yolo_rejection_message(reason: str) -> str:
    """Build rejection message from classifier reason."""
    try:
        from claude_code.utils.messages import build_yolo_rejection_message  # type: ignore[import]
        return build_yolo_rejection_message(reason)
    except ImportError:
        return f"Action blocked by auto mode classifier: {reason}"
