"""
hooks_types.py - Type definitions for Claude Code Hooks system.

Ported from: utils/hooks.ts (lines 1-400 type definitions)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    Union,
)
from typing_extensions import TypedDict, NotRequired

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOOL_HOOK_EXECUTION_TIMEOUT_MS: int = 10 * 60 * 1000
"""Default timeout for tool hooks (10 minutes in milliseconds)."""

SESSION_END_HOOK_TIMEOUT_MS_DEFAULT: int = 1500
"""
SessionEnd hooks run during shutdown/clear and need a much tighter bound
than TOOL_HOOK_EXECUTION_TIMEOUT_MS.
"""

# ---------------------------------------------------------------------------
# Hook Event Names (string literals)
# ---------------------------------------------------------------------------

HookEventName = Literal[
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "PermissionDenied",
    "SessionStart",
    "SessionEnd",
    "Setup",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "ConfigChange",
    "CwdChanged",
    "FileChanged",
    "InstructionsLoaded",
    "UserPromptSubmit",
    "Notification",
    "PreCompact",
    "PostCompact",
    "Elicitation",
    "ElicitationResult",
]

# Type alias for hook events (used in getMatchingHooks etc.)
HookEvent = HookEventName

# ---------------------------------------------------------------------------
# Permission/Decision types
# ---------------------------------------------------------------------------

PermissionBehavior = Literal["ask", "deny", "allow", "passthrough"]

ExitReason = Literal["normal", "error", "interrupt", "timeout"]

# ---------------------------------------------------------------------------
# Hook blocking error
# ---------------------------------------------------------------------------


@dataclass
class HookBlockingError:
    """Represents a blocking error returned by a hook."""
    blocking_error: str
    command: str


# ---------------------------------------------------------------------------
# ElicitationResponse (mirrors MCP SDK ElicitResult)
# ---------------------------------------------------------------------------


class ElicitationContentField(TypedDict, total=False):
    """Content field for elicitation response."""
    pass


class ElicitationResponse(TypedDict):
    """Re-export of ElicitResult for backward compatibility."""
    action: Literal["accept", "decline", "cancel"]
    content: NotRequired[Optional[Dict[str, Any]]]


# ---------------------------------------------------------------------------
# PermissionRequestResult
# ---------------------------------------------------------------------------


class PermissionRequestResultAllow(TypedDict):
    behavior: Literal["allow"]
    updated_input: NotRequired[Optional[Dict[str, Any]]]


class PermissionRequestResultDeny(TypedDict):
    behavior: Literal["deny"]
    reason: NotRequired[Optional[str]]


PermissionRequestResult = Union[PermissionRequestResultAllow, PermissionRequestResultDeny]

# ---------------------------------------------------------------------------
# HookResultMessage (simplified — references src/types/message.py)
# ---------------------------------------------------------------------------

# We use Any here to avoid circular imports; the real type is a union of
# message attachment variants defined in message.py.
HookResultMessage = Any

# ---------------------------------------------------------------------------
# HookResult
# ---------------------------------------------------------------------------


class HookResult(TypedDict, total=False):
    """Result returned by executing a single hook."""
    message: Optional[HookResultMessage]
    system_message: Optional[str]
    blocking_error: Optional[HookBlockingError]
    outcome: Literal["success", "blocking", "non_blocking_error", "cancelled"]
    prevent_continuation: Optional[bool]
    stop_reason: Optional[str]
    permission_behavior: Optional[PermissionBehavior]
    hook_permission_decision_reason: Optional[str]
    additional_context: Optional[str]
    initial_user_message: Optional[str]
    updated_input: Optional[Dict[str, Any]]
    updated_mcp_tool_output: Optional[Any]
    permission_request_result: Optional[PermissionRequestResult]
    elicitation_response: Optional[ElicitationResponse]
    watch_paths: Optional[List[str]]
    elicitation_result_response: Optional[ElicitationResponse]
    retry: Optional[bool]
    hook: Any  # HookCommand | HookCallback | FunctionHook


# ---------------------------------------------------------------------------
# AggregatedHookResult
# ---------------------------------------------------------------------------


class AggregatedHookResult(TypedDict, total=False):
    """Aggregated result from running all matching hooks for an event."""
    message: Optional[HookResultMessage]
    blocking_error: Optional[HookBlockingError]
    prevent_continuation: Optional[bool]
    stop_reason: Optional[str]
    hook_permission_decision_reason: Optional[str]
    hook_source: Optional[str]
    permission_behavior: Optional[PermissionBehavior]
    additional_contexts: Optional[List[str]]
    initial_user_message: Optional[str]
    updated_input: Optional[Dict[str, Any]]
    updated_mcp_tool_output: Optional[Any]
    permission_request_result: Optional[PermissionRequestResult]
    watch_paths: Optional[List[str]]
    elicitation_response: Optional[ElicitationResponse]
    elicitation_result_response: Optional[ElicitationResponse]
    retry: Optional[bool]


# ---------------------------------------------------------------------------
# Hook Input Types (from src/entrypoints/agentSdkTypes.ts)
# ---------------------------------------------------------------------------


class BaseHookInput(TypedDict):
    """Base fields common to all hook inputs."""
    hook_event_name: HookEventName
    session_id: str
    transcript_path: str
    cwd: str
    permission_mode: NotRequired[Optional[str]]
    agent_id: NotRequired[Optional[str]]
    agent_type: NotRequired[Optional[str]]


class PreToolUseHookInput(BaseHookInput):
    tool_name: str
    tool_input: Dict[str, Any]


class PostToolUseHookInput(BaseHookInput):
    tool_name: str
    tool_input: Dict[str, Any]
    tool_response: Any


class PostToolUseFailureHookInput(BaseHookInput):
    tool_name: str
    tool_input: Dict[str, Any]
    error: str


class PermissionDeniedHookInput(BaseHookInput):
    tool_name: str
    tool_input: Dict[str, Any]
    reason: str


class PermissionRequestHookInput(BaseHookInput):
    tool_name: str
    tool_input: Dict[str, Any]


class SessionStartHookInput(BaseHookInput):
    source: str


class SessionEndHookInput(BaseHookInput):
    reason: ExitReason


class SetupHookInput(BaseHookInput):
    trigger: str


class StopHookInput(BaseHookInput):
    pass


class StopFailureHookInput(BaseHookInput):
    error: str


class SubagentStartHookInput(BaseHookInput):
    agent_type: str


class SubagentStopHookInput(BaseHookInput):
    agent_type: str


class TeammateIdleHookInput(BaseHookInput):
    pass


class TaskCreatedHookInput(BaseHookInput):
    pass


class TaskCompletedHookInput(BaseHookInput):
    pass


class ConfigChangeHookInput(BaseHookInput):
    source: str


class CwdChangedHookInput(BaseHookInput):
    old_cwd: str
    new_cwd: str


class FileChangedHookInput(BaseHookInput):
    file_path: str
    change_type: str


class InstructionsLoadedHookInput(BaseHookInput):
    load_reason: str


class UserPromptSubmitHookInput(BaseHookInput):
    user_message: str


class NotificationHookInput(BaseHookInput):
    notification_type: str
    message: str


class PreCompactHookInput(BaseHookInput):
    trigger: str


class PostCompactHookInput(BaseHookInput):
    trigger: str


class ElicitationHookInput(BaseHookInput):
    mcp_server_name: str
    request_id: str
    message: str
    requested_schema: NotRequired[Optional[Dict[str, Any]]]


class ElicitationResultHookInput(BaseHookInput):
    mcp_server_name: str
    request_id: str
    action: str


# Union of all hook input types
HookInput = Union[
    PreToolUseHookInput,
    PostToolUseHookInput,
    PostToolUseFailureHookInput,
    PermissionDeniedHookInput,
    PermissionRequestHookInput,
    SessionStartHookInput,
    SessionEndHookInput,
    SetupHookInput,
    StopHookInput,
    StopFailureHookInput,
    SubagentStartHookInput,
    SubagentStopHookInput,
    TeammateIdleHookInput,
    TaskCreatedHookInput,
    TaskCompletedHookInput,
    ConfigChangeHookInput,
    CwdChangedHookInput,
    FileChangedHookInput,
    InstructionsLoadedHookInput,
    UserPromptSubmitHookInput,
    NotificationHookInput,
    PreCompactHookInput,
    PostCompactHookInput,
    ElicitationHookInput,
    ElicitationResultHookInput,
]

# ---------------------------------------------------------------------------
# Hook Command/Callback/Function types (from settings/types.ts)
# ---------------------------------------------------------------------------


class HookCommand(TypedDict, total=False):
    """A shell command hook."""
    type: Literal["command"]
    command: str
    timeout: Optional[int]  # seconds
    shell: Optional[Literal["bash", "powershell"]]
    async_: Optional[bool]   # 'async' is reserved in Python
    async_rewake: Optional[bool]
    if_: Optional[str]       # 'if' is reserved in Python


class HookCallbackBase(TypedDict):
    type: Literal["callback"]


class HookCallback(HookCallbackBase, total=False):
    """A JavaScript/internal callback hook."""
    internal: Optional[bool]
    matcher: Optional[str]


class FunctionHookBase(TypedDict):
    type: Literal["function"]


class FunctionHook(FunctionHookBase, total=False):
    """A Python function hook (session-scoped)."""
    fn: Optional[Callable[..., Any]]
    matcher: Optional[str]


# ---------------------------------------------------------------------------
# MatchedHook
# ---------------------------------------------------------------------------


@dataclass
class MatchedHook:
    """A hook paired with optional plugin context."""
    hook: Any  # HookCommand | HookCallback | FunctionHook
    plugin_root: Optional[str] = None
    plugin_id: Optional[str] = None
    skill_root: Optional[str] = None
    hook_source: Optional[str] = None  # 'settings' | 'plugin:<name>' | 'skill:<name>'


# ---------------------------------------------------------------------------
# Hook JSON Output types (sync/async)
# ---------------------------------------------------------------------------


class HookSpecificOutputPreToolUse(TypedDict, total=False):
    hookEventName: Literal["PreToolUse"]
    permissionDecision: Optional[Literal["allow", "deny", "ask"]]
    permissionDecisionReason: Optional[str]
    updatedInput: Optional[Dict[str, Any]]
    additionalContext: Optional[str]


class HookSpecificOutputUserPromptSubmit(TypedDict, total=False):
    hookEventName: Literal["UserPromptSubmit"]
    additionalContext: str


class HookSpecificOutputPostToolUse(TypedDict, total=False):
    hookEventName: Literal["PostToolUse"]
    additionalContext: Optional[str]
    updatedMCPToolOutput: Optional[Any]


class HookSpecificOutputSessionStart(TypedDict, total=False):
    hookEventName: Literal["SessionStart"]
    additionalContext: Optional[str]
    initialUserMessage: Optional[str]
    watchPaths: Optional[List[str]]


class HookSpecificOutputSetup(TypedDict, total=False):
    hookEventName: Literal["Setup"]
    additionalContext: Optional[str]


class HookSpecificOutputSubagentStart(TypedDict, total=False):
    hookEventName: Literal["SubagentStart"]
    additionalContext: Optional[str]


class HookSpecificOutputPostToolUseFailure(TypedDict, total=False):
    hookEventName: Literal["PostToolUseFailure"]
    additionalContext: Optional[str]


class HookSpecificOutputPermissionDenied(TypedDict, total=False):
    hookEventName: Literal["PermissionDenied"]
    retry: Optional[bool]


class HookSpecificOutputPermissionRequest(TypedDict, total=False):
    hookEventName: Literal["PermissionRequest"]
    decision: Optional[PermissionRequestResult]


class HookSpecificOutputElicitation(TypedDict, total=False):
    hookEventName: Literal["Elicitation"]
    action: Optional[Literal["accept", "decline", "cancel"]]
    content: Optional[Dict[str, Any]]


class HookSpecificOutputElicitationResult(TypedDict, total=False):
    hookEventName: Literal["ElicitationResult"]
    action: Optional[Literal["accept", "decline", "cancel"]]
    content: Optional[Dict[str, Any]]


HookSpecificOutput = Union[
    HookSpecificOutputPreToolUse,
    HookSpecificOutputUserPromptSubmit,
    HookSpecificOutputPostToolUse,
    HookSpecificOutputSessionStart,
    HookSpecificOutputSetup,
    HookSpecificOutputSubagentStart,
    HookSpecificOutputPostToolUseFailure,
    HookSpecificOutputPermissionDenied,
    HookSpecificOutputPermissionRequest,
    HookSpecificOutputElicitation,
    HookSpecificOutputElicitationResult,
]


class SyncHookJSONOutput(TypedDict, total=False):
    """Synchronous JSON output from a hook."""
    continue_: Optional[bool]       # 'continue' is reserved in Python
    suppress_output: Optional[bool]
    stop_reason: Optional[str]
    decision: Optional[Literal["approve", "block"]]
    reason: Optional[str]
    system_message: Optional[str]
    permission_decision: Optional[Literal["allow", "deny", "ask"]]
    hook_specific_output: Optional[HookSpecificOutput]
    # Raw dict form (from JSON) uses camelCase
    # We keep both for compatibility during JSON parsing


class AsyncHookJSONOutput(TypedDict, total=False):
    """Asynchronous hook output (hook signals it will run in background)."""
    async_: bool    # True means run in background
    async_timeout: Optional[int]


# Union of sync/async
HookJSONOutput = Union[SyncHookJSONOutput, AsyncHookJSONOutput]


def is_async_hook_json_output(obj: Any) -> bool:
    """Check if a parsed dict is an async hook output."""
    return isinstance(obj, dict) and obj.get("async") is True


def is_sync_hook_json_output(obj: Any) -> bool:
    """Check if a parsed dict is a sync hook output (not async)."""
    return isinstance(obj, dict) and obj.get("async") is not True


# ---------------------------------------------------------------------------
# PermissionUpdate (from agentSdkTypes)
# ---------------------------------------------------------------------------


class PermissionUpdate(TypedDict, total=False):
    tool_name: str
    behavior: PermissionBehavior
    reason: Optional[str]


# ---------------------------------------------------------------------------
# StatusLine / FileSuggestion hook event names (non-standard events)
# ---------------------------------------------------------------------------

# Extended hook event that includes internal/display events
ExtendedHookEvent = Union[HookEvent, Literal["StatusLine", "FileSuggestion"]]

# ---------------------------------------------------------------------------
# Exports for use by hooks_core.py and other modules
# ---------------------------------------------------------------------------

__all__ = [
    # Constants
    "TOOL_HOOK_EXECUTION_TIMEOUT_MS",
    "SESSION_END_HOOK_TIMEOUT_MS_DEFAULT",
    # Event types
    "HookEventName",
    "HookEvent",
    "ExtendedHookEvent",
    "ExitReason",
    "PermissionBehavior",
    # Core data types
    "HookBlockingError",
    "ElicitationResponse",
    "PermissionRequestResult",
    "PermissionRequestResultAllow",
    "PermissionRequestResultDeny",
    "HookResultMessage",
    "HookResult",
    "AggregatedHookResult",
    # Hook input types
    "BaseHookInput",
    "HookInput",
    "PreToolUseHookInput",
    "PostToolUseHookInput",
    "PostToolUseFailureHookInput",
    "PermissionDeniedHookInput",
    "PermissionRequestHookInput",
    "SessionStartHookInput",
    "SessionEndHookInput",
    "SetupHookInput",
    "StopHookInput",
    "StopFailureHookInput",
    "SubagentStartHookInput",
    "SubagentStopHookInput",
    "TeammateIdleHookInput",
    "TaskCreatedHookInput",
    "TaskCompletedHookInput",
    "ConfigChangeHookInput",
    "CwdChangedHookInput",
    "FileChangedHookInput",
    "InstructionsLoadedHookInput",
    "UserPromptSubmitHookInput",
    "NotificationHookInput",
    "PreCompactHookInput",
    "PostCompactHookInput",
    "ElicitationHookInput",
    "ElicitationResultHookInput",
    # Hook command/callback types
    "HookCommand",
    "HookCallback",
    "FunctionHook",
    "MatchedHook",
    # JSON output types
    "SyncHookJSONOutput",
    "AsyncHookJSONOutput",
    "HookJSONOutput",
    "HookSpecificOutput",
    "is_async_hook_json_output",
    "is_sync_hook_json_output",
    # Permission types
    "PermissionUpdate",
]
