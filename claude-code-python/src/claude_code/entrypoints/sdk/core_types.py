"""
SDK Core Types - Common serializable types used by both SDK consumers and SDK builders.

Types mirror the TypeScript core types from sdk/coreTypes.ts.
Re-exports sandbox types and defines runtime-usable const arrays.
"""

from __future__ import annotations

# Re-export sandbox types for SDK consumers
from claude_code.entrypoints.sandbox_types import (
    SandboxFilesystemConfig,
    SandboxIgnoreViolations,
    SandboxNetworkConfig,
    SandboxSettings,
)

# Re-export all generated types (from core_schemas)
from claude_code.entrypoints.sdk.core_schemas import (
    # Usage & model types
    ModelUsageSchema,
    # Output format
    OutputFormatTypeSchema,
    BaseOutputFormatSchema,
    JsonSchemaOutputFormatSchema,
    OutputFormatSchema,
    # Config
    ApiKeySourceSchema,
    ConfigScopeSchema,
    SdkBetaSchema,
    ThinkingAdaptiveSchema,
    ThinkingEnabledSchema,
    ThinkingDisabledSchema,
    ThinkingConfigSchema,
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
    # Permissions
    PermissionUpdateDestinationSchema,
    PermissionBehaviorSchema,
    PermissionRuleValueSchema,
    PermissionUpdateSchema,
    PermissionDecisionClassificationSchema,
    PermissionResultSchema,
    PermissionModeSchema,
    # Hooks
    HOOK_EVENTS,
    HookEventSchema,
    BaseHookInputSchema,
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
    ConfigChangeHookInputSchema,
    InstructionsLoadedHookInputSchema,
    WorktreeCreateHookInputSchema,
    WorktreeRemoveHookInputSchema,
    CwdChangedHookInputSchema,
    FileChangedHookInputSchema,
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
    # Skills/Commands
    SlashCommandSchema,
    AgentInfoSchema,
    ModelInfoSchema,
    AccountInfoSchema,
    # Agent definitions
    AgentMcpServerSpecSchema,
    AgentDefinitionSchema,
    # Settings
    SettingSourceSchema,
    SdkPluginConfigSchema,
    # Rewind
    RewindFilesResultSchema,
    # SDK messages
    SDKAssistantMessageErrorSchema,
    SDKStatusSchema,
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
    SDKMessageSchema,
    FastModeStateSchema,
    # Constants
    EXIT_REASONS,
    ExitReasonSchema,
    CONFIG_CHANGE_SOURCES,
    INSTRUCTIONS_LOAD_REASONS,
    INSTRUCTIONS_MEMORY_TYPES,
)

__all__ = [
    # sandbox types
    "SandboxFilesystemConfig",
    "SandboxIgnoreViolations",
    "SandboxNetworkConfig",
    "SandboxSettings",
    # const arrays
    "HOOK_EVENTS",
    "EXIT_REASONS",
]
