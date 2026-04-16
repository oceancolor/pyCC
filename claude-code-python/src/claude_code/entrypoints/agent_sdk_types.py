"""
Agent SDK Types - Main entrypoint for Claude Code Agent SDK types.

This file re-exports the public SDK API from:
- sdk/core_types.py - Common serializable types (messages, configs)
- (runtime types would be in sdk/runtime_types.py if implemented)

SDK builders who need control protocol types should import from
sdk/control_schemas.py directly.

Corresponds to agentSdkTypes.ts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

# Control protocol types for SDK builders
from claude_code.entrypoints.sdk.control_schemas import (
    SDKControlRequest,
    SDKControlResponse,
)

# Re-export core types (common serializable types)
from claude_code.entrypoints.sdk.core_types import (
    SandboxFilesystemConfig,
    SandboxIgnoreViolations,
    SandboxNetworkConfig,
    SandboxSettings,
    HOOK_EVENTS,
    EXIT_REASONS,
)

from claude_code.entrypoints.sdk.core_schemas import (
    # Usage & model types
    ModelUsageSchema,
    ModelUsage,
    # Output format
    OutputFormatTypeSchema,
    BaseOutputFormatSchema,
    JsonSchemaOutputFormatSchema,
    OutputFormatSchema,
    JsonSchemaOutputFormat,
    OutputFormat,
    # Config
    ApiKeySourceSchema,
    ApiKeySource,
    ConfigScopeSchema,
    ConfigScope,
    SdkBetaSchema,
    SdkBeta,
    ThinkingAdaptiveSchema,
    ThinkingEnabledSchema,
    ThinkingDisabledSchema,
    ThinkingConfigSchema,
    ThinkingAdaptive,
    ThinkingEnabled,
    ThinkingDisabled,
    ThinkingConfig,
    # MCP server configs
    McpStdioServerConfigSchema,
    McpSSEServerConfigSchema,
    McpHttpServerConfigSchema,
    McpSdkServerConfigSchema,
    McpServerConfigForProcessTransportSchema,
    McpClaudeAIProxyServerConfigSchema,
    McpServerStatusConfigSchema,
    McpServerStatusSchema,
    McpSetServersResultSchema,
    McpStdioServerConfig,
    McpSSEServerConfig,
    McpHttpServerConfig,
    McpSdkServerConfig,
    McpServerConfigForProcessTransport,
    McpClaudeAIProxyServerConfig,
    McpServerStatusConfig,
    McpSetServersResult,
    # Permissions
    PermissionUpdateDestinationSchema,
    PermissionBehaviorSchema,
    PermissionRuleValueSchema,
    PermissionUpdateSchema,
    PermissionDecisionClassificationSchema,
    PermissionResultSchema,
    PermissionModeSchema,
    PermissionUpdateDestination,
    PermissionBehavior,
    PermissionDecisionClassification,
    PermissionMode,
    PermissionRuleValue,
    # Hooks
    HOOK_EVENTS,
    HookEventSchema,
    HookEvent,
    BaseHookInputSchema,
    BaseHookInput,
    PreToolUseHookInputSchema,
    PermissionRequestHookInputSchema,
    PostToolUseHookInputSchema,
    PostToolUseFailureHookInputSchema,
    PermissionDeniedHookInputSchema,
    NotificationHookInputSchema,
    UserPromptSubmitHookInputSchema,
    SessionStartHookInputSchema,
    SessionEndHookInputSchema,
    StopHookInputSchema,
    StopFailureHookInputSchema,
    SubagentStartHookInputSchema,
    SubagentStopHookInputSchema,
    PreCompactHookInputSchema,
    PostCompactHookInputSchema,
    SetupHookInputSchema,
    TeammateIdleHookInputSchema,
    TaskCreatedHookInputSchema,
    TaskCompletedHookInputSchema,
    ElicitationHookInputSchema,
    ElicitationResultHookInputSchema,
    CONFIG_CHANGE_SOURCES,
    ConfigChangeHookInputSchema,
    INSTRUCTIONS_LOAD_REASONS,
    INSTRUCTIONS_MEMORY_TYPES,
    InstructionsLoadedHookInputSchema,
    WorktreeCreateHookInputSchema,
    WorktreeRemoveHookInputSchema,
    CwdChangedHookInputSchema,
    FileChangedHookInputSchema,
    EXIT_REASONS,
    ExitReasonSchema,
    ExitReason,
    HookInputSchema,
    # Hook outputs
    AsyncHookJSONOutputSchema,
    PreToolUseHookSpecificOutputSchema,
    UserPromptSubmitHookSpecificOutputSchema,
    SessionStartHookSpecificOutputSchema,
    SetupHookSpecificOutputSchema,
    SubagentStartHookSpecificOutputSchema,
    PostToolUseHookSpecificOutputSchema,
    PostToolUseFailureHookSpecificOutputSchema,
    PermissionDeniedHookSpecificOutputSchema,
    NotificationHookSpecificOutputSchema,
    PermissionRequestHookSpecificOutputSchema,
    ElicitationHookSpecificOutputSchema,
    ElicitationResultHookSpecificOutputSchema,
    CwdChangedHookSpecificOutputSchema,
    FileChangedHookSpecificOutputSchema,
    SyncHookJSONOutputSchema,
    WorktreeCreateHookSpecificOutputSchema,
    HookJSONOutputSchema,
    # Prompts
    PromptRequestOptionSchema,
    PromptRequestSchema,
    PromptResponseSchema,
    PromptRequestOption,
    PromptRequest,
    PromptResponse,
    # Skills/Commands
    SlashCommandSchema,
    AgentInfoSchema,
    ModelInfoSchema,
    AccountInfoSchema,
    SlashCommand,
    AgentInfo,
    ModelInfo,
    AccountInfo,
    # Agent definitions
    AgentMcpServerSpecSchema,
    AgentDefinitionSchema,
    AgentDefinition,
    # Settings
    SettingSourceSchema,
    SettingSource,
    SdkPluginConfigSchema,
    SdkPluginConfig,
    # Rewind
    RewindFilesResultSchema,
    RewindFilesResult,
    # SDK messages
    SDKAssistantMessageErrorSchema,
    SDKAssistantMessageError,
    SDKStatusSchema,
    FastModeStateSchema,
    FastModeState,
    SDKUserMessageSchema,
    SDKUserMessageReplaySchema,
    SDKRateLimitInfoSchema,
    SDKAssistantMessageSchema,
    SDKRateLimitEventSchema,
    SDKStreamlinedTextMessageSchema,
    SDKStreamlinedToolUseSummaryMessageSchema,
    SDKPermissionDenialSchema,
    SDKResultSuccessSchema,
    SDKResultErrorSchema,
    SDKResultMessageSchema,
    SDKSystemMessageSchema,
    SDKPartialAssistantMessageSchema,
    SDKCompactBoundaryMessageSchema,
    SDKStatusMessageSchema,
    SDKPostTurnSummaryMessageSchema,
    SDKAPIRetryMessageSchema,
    SDKLocalCommandOutputMessageSchema,
    SDKHookStartedMessageSchema,
    SDKHookProgressMessageSchema,
    SDKHookResponseMessageSchema,
    SDKToolProgressMessageSchema,
    SDKAuthStatusMessageSchema,
    SDKFilesPersistedEventSchema,
    SDKTaskNotificationMessageSchema,
    SDKTaskStartedMessageSchema,
    SDKTaskProgressMessageSchema,
    SDKSessionStateChangedMessageSchema,
    SDKToolUseSummaryMessageSchema,
    SDKElicitationCompleteMessageSchema,
    SDKPromptSuggestionMessageSchema,
    SDKSessionInfoSchema,
    SDKSessionInfo,
    SDKMessageSchema,
)

# ============================================================================
# Agent SDK functions (stub implementations — raise NotImplementedError)
# ============================================================================
# These stub out the TypeScript SDK functions that can't be fully implemented
# in the type stub layer. Callers from the actual Python SDK override these.


class AbortError(Exception):
    """Equivalent of TypeScript's AbortError."""
    pass


def tool(
    name: str,
    description: str,
    input_schema: Dict[str, Any],
    handler: Any,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Define an MCP tool for use with the SDK.

    Stub — not implemented in the type layer.
    """
    raise NotImplementedError("tool() is not implemented in the SDK type stub")


class _CreateSdkMcpServerOptions:
    """Options for create_sdk_mcp_server."""
    def __init__(
        self,
        name: str,
        version: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        self.name = name
        self.version = version
        self.tools = tools or []


def create_sdk_mcp_server(options: _CreateSdkMcpServerOptions) -> Dict[str, Any]:
    """
    Creates an MCP server instance that can be used with the SDK transport.

    Stub — not implemented in the type layer.
    """
    raise NotImplementedError("create_sdk_mcp_server() is not implemented in the SDK type stub")


def query(params: Dict[str, Any]) -> Any:
    """
    Query Claude Code with a prompt or message stream.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("query is not implemented in the SDK")


def unstable_v2_create_session(options: Dict[str, Any]) -> Any:
    """
    V2 API - UNSTABLE
    Create a persistent session for multi-turn conversations.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("unstable_v2_create_session is not implemented in the SDK")


def unstable_v2_resume_session(session_id: str, options: Dict[str, Any]) -> Any:
    """
    V2 API - UNSTABLE
    Resume an existing session by ID.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("unstable_v2_resume_session is not implemented in the SDK")


async def unstable_v2_prompt(message: str, options: Dict[str, Any]) -> Any:
    """
    V2 API - UNSTABLE
    One-shot convenience function for single prompts.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("unstable_v2_prompt is not implemented in the SDK")


async def get_session_messages(
    session_id: str,
    options: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Reads a session's conversation messages from its JSONL transcript file.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("get_session_messages is not implemented in the SDK")


async def list_sessions(
    options: Optional[Dict[str, Any]] = None,
) -> List[SDKSessionInfo]:
    """
    List sessions with metadata.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("list_sessions is not implemented in the SDK")


async def get_session_info(
    session_id: str,
    options: Optional[Dict[str, Any]] = None,
) -> Optional[SDKSessionInfo]:
    """
    Reads metadata for a single session by ID.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("get_session_info is not implemented in the SDK")


async def rename_session(
    session_id: str,
    title: str,
    options: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Rename a session.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("rename_session is not implemented in the SDK")


async def tag_session(
    session_id: str,
    tag: Optional[str],
    options: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Tag a session. Pass None to clear the tag.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("tag_session is not implemented in the SDK")


async def fork_session(
    session_id: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Fork a session into a new branch with fresh UUIDs.

    Stub — not implemented in the SDK type layer.
    """
    raise NotImplementedError("fork_session is not implemented in the SDK")


# ============================================================================
# Assistant daemon primitives (internal)
# ============================================================================

class CronTask:
    """
    A scheduled task from <dir>/.claude/scheduled_tasks.json.

    @internal
    """
    def __init__(
        self,
        id: str,
        cron: str,
        prompt: str,
        created_at: int,
        recurring: Optional[bool] = None,
    ):
        self.id = id
        self.cron = cron
        self.prompt = prompt
        self.created_at = created_at
        self.recurring = recurring


class CronJitterConfig:
    """
    Cron scheduler tuning knobs (jitter + expiry).

    @internal
    """
    def __init__(
        self,
        recurring_frac: float,
        recurring_cap_ms: int,
        one_shot_max_ms: int,
        one_shot_floor_ms: int,
        one_shot_minute_mod: int,
        recurring_max_age_ms: int,
    ):
        self.recurring_frac = recurring_frac
        self.recurring_cap_ms = recurring_cap_ms
        self.one_shot_max_ms = one_shot_max_ms
        self.one_shot_floor_ms = one_shot_floor_ms
        self.one_shot_minute_mod = one_shot_minute_mod
        self.recurring_max_age_ms = recurring_max_age_ms


# ScheduledTaskEvent is a union of fire and missed events
ScheduledTaskEvent = Union[
    Dict[str, Any],  # { type: 'fire', task: CronTask }
    Dict[str, Any],  # { type: 'missed', tasks: List[CronTask] }
]


class ScheduledTasksHandle:
    """
    Handle returned by watch_scheduled_tasks().

    @internal
    """
    async def events(self):
        """Async generator of fire/missed events. Drain with async for."""
        raise NotImplementedError
        yield  # make it an async generator

    def get_next_fire_time(self) -> Optional[int]:
        """
        Epoch ms of the soonest scheduled fire across all loaded tasks,
        or None if nothing is scheduled.
        """
        raise NotImplementedError


def watch_scheduled_tasks(
    dir: str,
    signal: Any,  # AbortSignal equivalent
    get_jitter_config: Optional[Any] = None,
) -> ScheduledTasksHandle:
    """
    Watch <dir>/.claude/scheduled_tasks.json and yield events as tasks fire.

    @internal — stub only.
    """
    raise NotImplementedError("watch_scheduled_tasks is not implemented in the SDK type stub")


def build_missed_task_notification(missed: List[CronTask]) -> str:
    """
    Format missed one-shot tasks into a prompt.

    @internal — stub only.
    """
    raise NotImplementedError("build_missed_task_notification is not implemented in the SDK type stub")


class InboundPrompt:
    """
    A user message typed on claude.ai, extracted from the bridge WS.

    @internal
    """
    def __init__(
        self,
        content: Union[str, List[Any]],
        uuid: Optional[str] = None,
    ):
        self.content = content
        self.uuid = uuid


class ConnectRemoteControlOptions:
    """
    Options for connect_remote_control.

    @internal
    """
    def __init__(
        self,
        dir: str,
        name: Optional[str] = None,
        worker_type: Optional[str] = None,
        branch: Optional[str] = None,
        git_repo_url: Optional[str] = None,
        get_access_token: Any = None,
        base_url: str = "",
        org_uuid: str = "",
        model: str = "",
    ):
        self.dir = dir
        self.name = name
        self.worker_type = worker_type
        self.branch = branch
        self.git_repo_url = git_repo_url
        self.get_access_token = get_access_token
        self.base_url = base_url
        self.org_uuid = org_uuid
        self.model = model


class RemoteControlHandle:
    """
    Handle returned by connect_remote_control.

    @internal
    """
    session_url: str = ""
    environment_id: str = ""
    bridge_session_id: str = ""

    def write(self, msg: Any) -> None:
        raise NotImplementedError

    def send_result(self) -> None:
        raise NotImplementedError

    def send_control_request(self, req: Any) -> None:
        raise NotImplementedError

    def send_control_response(self, res: Any) -> None:
        raise NotImplementedError

    def send_control_cancel_request(self, request_id: str) -> None:
        raise NotImplementedError

    async def inbound_prompts(self):
        raise NotImplementedError
        yield

    async def control_requests(self):
        raise NotImplementedError
        yield

    async def permission_responses(self):
        raise NotImplementedError
        yield

    def on_state_change(self, cb: Any) -> None:
        raise NotImplementedError

    async def teardown(self) -> None:
        raise NotImplementedError


async def connect_remote_control(
    opts: ConnectRemoteControlOptions,
) -> Optional[RemoteControlHandle]:
    """
    Hold a claude.ai remote-control bridge connection from a daemon process.

    @internal — stub only. Returns None on no-OAuth or registration failure.
    """
    raise NotImplementedError("connect_remote_control is not implemented in the SDK type stub")
