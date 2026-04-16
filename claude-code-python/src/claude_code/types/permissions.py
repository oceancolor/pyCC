"""
Permission type definitions
原始 TS: src/types/permissions.ts

注意：bun:bundle feature() 调用均替换为运行时环境变量检查
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union

# ---------------------------------------------------------------------------
# Permission Modes
# ---------------------------------------------------------------------------

EXTERNAL_PERMISSION_MODES = (
    "acceptEdits",
    "bypassPermissions",
    "default",
    "dontAsk",
    "plan",
)

ExternalPermissionMode = Literal[
    "acceptEdits",
    "bypassPermissions",
    "default",
    "dontAsk",
    "plan",
]

InternalPermissionMode = Literal[
    "acceptEdits",
    "bypassPermissions",
    "default",
    "dontAsk",
    "plan",
    "auto",
    "bubble",
]

PermissionMode = InternalPermissionMode

# ---------------------------------------------------------------------------
# Permission Behaviors
# ---------------------------------------------------------------------------

PermissionBehavior = Literal["allow", "deny", "ask"]

# ---------------------------------------------------------------------------
# Permission Rules
# ---------------------------------------------------------------------------

PermissionRuleSource = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
    "cliArg",
    "command",
    "session",
]


@dataclass
class PermissionRuleValue:
    tool_name: str
    rule_content: Optional[str] = None


@dataclass
class PermissionRule:
    source: PermissionRuleSource
    rule_behavior: PermissionBehavior
    rule_value: PermissionRuleValue


# ---------------------------------------------------------------------------
# Permission Updates
# ---------------------------------------------------------------------------

PermissionUpdateDestination = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "session",
    "cliArg",
]


@dataclass
class PermissionUpdateAddRules:
    type: Literal["addRules"] = "addRules"
    destination: PermissionUpdateDestination = "session"
    rules: list[PermissionRuleValue] = field(default_factory=list)
    behavior: PermissionBehavior = "ask"


@dataclass
class PermissionUpdateReplaceRules:
    type: Literal["replaceRules"] = "replaceRules"
    destination: PermissionUpdateDestination = "session"
    rules: list[PermissionRuleValue] = field(default_factory=list)
    behavior: PermissionBehavior = "ask"


@dataclass
class PermissionUpdateRemoveRules:
    type: Literal["removeRules"] = "removeRules"
    destination: PermissionUpdateDestination = "session"
    rules: list[PermissionRuleValue] = field(default_factory=list)
    behavior: PermissionBehavior = "ask"


@dataclass
class PermissionUpdateSetMode:
    type: Literal["setMode"] = "setMode"
    destination: PermissionUpdateDestination = "session"
    mode: ExternalPermissionMode = "default"


@dataclass
class PermissionUpdateAddDirectories:
    type: Literal["addDirectories"] = "addDirectories"
    destination: PermissionUpdateDestination = "session"
    directories: list[str] = field(default_factory=list)


@dataclass
class PermissionUpdateRemoveDirectories:
    type: Literal["removeDirectories"] = "removeDirectories"
    destination: PermissionUpdateDestination = "session"
    directories: list[str] = field(default_factory=list)


PermissionUpdate = Union[
    PermissionUpdateAddRules,
    PermissionUpdateReplaceRules,
    PermissionUpdateRemoveRules,
    PermissionUpdateSetMode,
    PermissionUpdateAddDirectories,
    PermissionUpdateRemoveDirectories,
]

WorkingDirectorySource = PermissionRuleSource


@dataclass
class AdditionalWorkingDirectory:
    path: str
    source: WorkingDirectorySource


# ---------------------------------------------------------------------------
# Permission Decisions & Results
# ---------------------------------------------------------------------------

@dataclass
class PermissionCommandMetadata:
    name: str
    description: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


PermissionMetadata = Optional[dict]  # { command: PermissionCommandMetadata } | undefined


@dataclass
class PendingClassifierCheck:
    command: str
    cwd: str
    descriptions: list[str]


@dataclass
class PermissionAllowDecision:
    behavior: Literal["allow"] = "allow"
    updated_input: Optional[dict[str, Any]] = None
    user_modified: Optional[bool] = None
    decision_reason: Optional[Any] = None   # PermissionDecisionReason
    tool_use_id: Optional[str] = None
    accept_feedback: Optional[str] = None
    content_blocks: Optional[list[Any]] = None  # ContentBlockParam[]


@dataclass
class PermissionAskDecision:
    behavior: Literal["ask"] = "ask"
    message: str = ""
    updated_input: Optional[dict[str, Any]] = None
    decision_reason: Optional[Any] = None
    suggestions: Optional[list[PermissionUpdate]] = None
    blocked_path: Optional[str] = None
    metadata: Optional[PermissionMetadata] = None
    is_bash_security_check_for_misparsing: Optional[bool] = None
    pending_classifier_check: Optional[PendingClassifierCheck] = None
    content_blocks: Optional[list[Any]] = None


@dataclass
class PermissionDenyDecision:
    behavior: Literal["deny"] = "deny"
    message: str = ""
    decision_reason: Optional[Any] = None
    tool_use_id: Optional[str] = None


PermissionDecision = Union[
    PermissionAllowDecision,
    PermissionAskDecision,
    PermissionDenyDecision,
]


@dataclass
class PermissionPassthroughResult:
    behavior: Literal["passthrough"] = "passthrough"
    message: str = ""
    decision_reason: Optional[Any] = None
    suggestions: Optional[list[PermissionUpdate]] = None
    blocked_path: Optional[str] = None
    pending_classifier_check: Optional[PendingClassifierCheck] = None


PermissionResult = Union[
    PermissionDecision,
    PermissionPassthroughResult,
]

# ---------------------------------------------------------------------------
# PermissionDecisionReason (discriminated union)
# ---------------------------------------------------------------------------

@dataclass
class PermissionDecisionReasonRule:
    type: Literal["rule"] = "rule"
    rule: Optional[PermissionRule] = None


@dataclass
class PermissionDecisionReasonMode:
    type: Literal["mode"] = "mode"
    mode: Optional[PermissionMode] = None


@dataclass
class PermissionDecisionReasonSubcommand:
    type: Literal["subcommandResults"] = "subcommandResults"
    reasons: Optional[dict[str, Any]] = None  # Map<string, PermissionResult>


@dataclass
class PermissionDecisionReasonPermissionPromptTool:
    type: Literal["permissionPromptTool"] = "permissionPromptTool"
    permission_prompt_tool_name: str = ""
    tool_result: Optional[Any] = None


@dataclass
class PermissionDecisionReasonHook:
    type: Literal["hook"] = "hook"
    hook_name: str = ""
    hook_source: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class PermissionDecisionReasonAsyncAgent:
    type: Literal["asyncAgent"] = "asyncAgent"
    reason: str = ""


@dataclass
class PermissionDecisionReasonSandboxOverride:
    type: Literal["sandboxOverride"] = "sandboxOverride"
    reason: Literal["excludedCommand", "dangerouslyDisableSandbox"] = "excludedCommand"


@dataclass
class PermissionDecisionReasonClassifier:
    type: Literal["classifier"] = "classifier"
    classifier: str = ""
    reason: str = ""


@dataclass
class PermissionDecisionReasonWorkingDir:
    type: Literal["workingDir"] = "workingDir"
    reason: str = ""


@dataclass
class PermissionDecisionReasonSafetyCheck:
    type: Literal["safetyCheck"] = "safetyCheck"
    reason: str = ""
    classifier_approvable: bool = False


@dataclass
class PermissionDecisionReasonOther:
    type: Literal["other"] = "other"
    reason: str = ""


PermissionDecisionReason = Union[
    PermissionDecisionReasonRule,
    PermissionDecisionReasonMode,
    PermissionDecisionReasonSubcommand,
    PermissionDecisionReasonPermissionPromptTool,
    PermissionDecisionReasonHook,
    PermissionDecisionReasonAsyncAgent,
    PermissionDecisionReasonSandboxOverride,
    PermissionDecisionReasonClassifier,
    PermissionDecisionReasonWorkingDir,
    PermissionDecisionReasonSafetyCheck,
    PermissionDecisionReasonOther,
]

# ---------------------------------------------------------------------------
# Bash Classifier Types
# ---------------------------------------------------------------------------

@dataclass
class ClassifierResult:
    matches: bool
    confidence: Literal["high", "medium", "low"] = "medium"
    reason: str = ""
    matched_description: Optional[str] = None


ClassifierBehavior = Literal["deny", "ask", "allow"]


@dataclass
class ClassifierUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class YoloClassifierResult:
    should_block: bool
    model: str
    reason: str = ""
    thinking: Optional[str] = None
    unavailable: Optional[bool] = None
    transcript_too_long: Optional[bool] = None
    usage: Optional[ClassifierUsage] = None
    duration_ms: Optional[int] = None
    prompt_lengths: Optional[dict[str, int]] = None
    error_dump_path: Optional[str] = None
    stage: Optional[Literal["fast", "thinking"]] = None
    stage1_usage: Optional[ClassifierUsage] = None
    stage1_duration_ms: Optional[int] = None
    stage1_request_id: Optional[str] = None
    stage1_msg_id: Optional[str] = None
    stage2_usage: Optional[ClassifierUsage] = None
    stage2_duration_ms: Optional[int] = None
    stage2_request_id: Optional[str] = None
    stage2_msg_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Permission Explainer Types
# ---------------------------------------------------------------------------

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass
class PermissionExplanation:
    risk_level: RiskLevel
    explanation: str
    reasoning: str
    risk: str


# ---------------------------------------------------------------------------
# Tool Permission Context
# ---------------------------------------------------------------------------

ToolPermissionRulesBySource = dict  # { [PermissionRuleSource]: list[str] }


@dataclass
class ToolPermissionContext:
    mode: PermissionMode
    additional_working_directories: dict[str, AdditionalWorkingDirectory]  # ReadonlyMap
    always_allow_rules: ToolPermissionRulesBySource
    always_deny_rules: ToolPermissionRulesBySource
    always_ask_rules: ToolPermissionRulesBySource
    is_bypass_permissions_mode_available: bool
    stripped_dangerous_rules: Optional[ToolPermissionRulesBySource] = None
    should_avoid_permission_prompts: Optional[bool] = None
    await_automated_checks_before_dialog: Optional[bool] = None
    pre_plan_mode: Optional[PermissionMode] = None
