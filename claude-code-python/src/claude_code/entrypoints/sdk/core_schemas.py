"""
SDK Core Schemas - Schema descriptions for serializable SDK data types.

These schemas are the single source of truth for SDK data types.
TypeScript Zod schemas are represented here as Python dicts (schema metadata)
and TypedDicts for type-checked usage.

Corresponds to sdk/coreSchemas.ts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from typing import TypedDict


# ============================================================================
# Usage & Model Types
# ============================================================================

ModelUsageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "inputTokens": {"type": "number"},
        "outputTokens": {"type": "number"},
        "cacheReadInputTokens": {"type": "number"},
        "cacheCreationInputTokens": {"type": "number"},
        "webSearchRequests": {"type": "number"},
        "costUSD": {"type": "number"},
        "contextWindow": {"type": "number"},
        "maxOutputTokens": {"type": "number"},
    },
}


class ModelUsage(TypedDict):
    inputTokens: int
    outputTokens: int
    cacheReadInputTokens: int
    cacheCreationInputTokens: int
    webSearchRequests: int
    costUSD: float
    contextWindow: int
    maxOutputTokens: int


# ============================================================================
# Output Format Types
# ============================================================================

OutputFormatTypeSchema: Dict[str, Any] = {"type": "literal", "value": "json_schema"}

BaseOutputFormatSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": OutputFormatTypeSchema,
    },
}

JsonSchemaOutputFormatSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "json_schema"},
        "schema": {"type": "record", "key": "string", "value": "unknown"},
    },
}

OutputFormatSchema: Dict[str, Any] = JsonSchemaOutputFormatSchema


class JsonSchemaOutputFormat(TypedDict):
    type: Literal["json_schema"]
    schema: Dict[str, Any]


OutputFormat = JsonSchemaOutputFormat


# ============================================================================
# Config Types
# ============================================================================

ApiKeySourceSchema: Dict[str, Any] = {
    "type": "enum",
    "values": ["user", "project", "org", "temporary", "oauth"],
}

ApiKeySource = Literal["user", "project", "org", "temporary", "oauth"]

ConfigScopeSchema: Dict[str, Any] = {
    "type": "enum",
    "values": ["local", "user", "project"],
    "description": "Config scope for settings.",
}

ConfigScope = Literal["local", "user", "project"]

SdkBetaSchema: Dict[str, Any] = {
    "type": "literal",
    "value": "context-1m-2025-08-07",
}

SdkBeta = Literal["context-1m-2025-08-07"]

ThinkingAdaptiveSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Claude decides when and how much to think (Opus 4.6+).",
    "properties": {
        "type": {"type": "literal", "value": "adaptive"},
    },
}

ThinkingEnabledSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Fixed thinking token budget (older models)",
    "properties": {
        "type": {"type": "literal", "value": "enabled"},
        "budgetTokens": {"type": "number", "optional": True},
    },
}

ThinkingDisabledSchema: Dict[str, Any] = {
    "type": "object",
    "description": "No extended thinking",
    "properties": {
        "type": {"type": "literal", "value": "disabled"},
    },
}

ThinkingConfigSchema: Dict[str, Any] = {
    "type": "union",
    "description": "Controls Claude's thinking/reasoning behavior. When set, takes precedence over the deprecated maxThinkingTokens.",
    "variants": [ThinkingAdaptiveSchema, ThinkingEnabledSchema, ThinkingDisabledSchema],
}


class ThinkingAdaptive(TypedDict):
    type: Literal["adaptive"]


class ThinkingEnabled(TypedDict, total=False):
    type: Literal["enabled"]
    budgetTokens: int


class ThinkingDisabled(TypedDict):
    type: Literal["disabled"]


ThinkingConfig = Union[ThinkingAdaptive, ThinkingEnabled, ThinkingDisabled]


# ============================================================================
# MCP Server Config Types (serializable only)
# ============================================================================

McpStdioServerConfigSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "stdio", "optional": True},
        "command": {"type": "string"},
        "args": {"type": "array", "items": {"type": "string"}, "optional": True},
        "env": {"type": "record", "key": "string", "value": "string", "optional": True},
    },
}

McpSSEServerConfigSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "sse"},
        "url": {"type": "string"},
        "headers": {"type": "record", "key": "string", "value": "string", "optional": True},
    },
}

McpHttpServerConfigSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "http"},
        "url": {"type": "string"},
        "headers": {"type": "record", "key": "string", "value": "string", "optional": True},
    },
}

McpSdkServerConfigSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "sdk"},
        "name": {"type": "string"},
    },
}

McpServerConfigForProcessTransportSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [
        McpStdioServerConfigSchema,
        McpSSEServerConfigSchema,
        McpHttpServerConfigSchema,
        McpSdkServerConfigSchema,
    ],
}

McpClaudeAIProxyServerConfigSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "claudeai-proxy"},
        "url": {"type": "string"},
        "id": {"type": "string"},
    },
}

McpServerStatusConfigSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [McpServerConfigForProcessTransportSchema, McpClaudeAIProxyServerConfigSchema],
}

McpServerStatusSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Status information for an MCP server connection.",
    "properties": {
        "name": {"type": "string", "description": "Server name as configured"},
        "status": {
            "type": "enum",
            "values": ["connected", "failed", "needs-auth", "pending", "disabled"],
            "description": "Current connection status",
        },
        "serverInfo": {
            "type": "object",
            "optional": True,
            "properties": {"name": {"type": "string"}, "version": {"type": "string"}},
        },
        "error": {"type": "string", "optional": True},
        "config": {**McpServerStatusConfigSchema, "optional": True},
        "scope": {"type": "string", "optional": True},
        "tools": {"type": "array", "optional": True, "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string", "optional": True},
                "annotations": {"type": "object", "optional": True},
            },
        }},
        "capabilities": {"type": "object", "optional": True},
    },
}

McpSetServersResultSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Result of a setMcpServers operation.",
    "properties": {
        "added": {"type": "array", "items": {"type": "string"}},
        "removed": {"type": "array", "items": {"type": "string"}},
        "errors": {"type": "record", "key": "string", "value": "string"},
    },
}


class McpStdioServerConfig(TypedDict, total=False):
    type: Literal["stdio"]
    command: str
    args: List[str]
    env: Dict[str, str]


class McpSSEServerConfig(TypedDict, total=False):
    type: Literal["sse"]
    url: str
    headers: Dict[str, str]


class McpHttpServerConfig(TypedDict, total=False):
    type: Literal["http"]
    url: str
    headers: Dict[str, str]


class McpSdkServerConfig(TypedDict):
    type: Literal["sdk"]
    name: str


McpServerConfigForProcessTransport = Union[
    McpStdioServerConfig, McpSSEServerConfig, McpHttpServerConfig, McpSdkServerConfig
]


class McpClaudeAIProxyServerConfig(TypedDict):
    type: Literal["claudeai-proxy"]
    url: str
    id: str


McpServerStatusConfig = Union[McpServerConfigForProcessTransport, McpClaudeAIProxyServerConfig]


class McpSetServersResult(TypedDict):
    added: List[str]
    removed: List[str]
    errors: Dict[str, str]


# ============================================================================
# Permission Types
# ============================================================================

PermissionUpdateDestinationSchema: Dict[str, Any] = {
    "type": "enum",
    "values": ["userSettings", "projectSettings", "localSettings", "session", "cliArg"],
}

PermissionBehaviorSchema: Dict[str, Any] = {
    "type": "enum",
    "values": ["allow", "deny", "ask"],
}

PermissionRuleValueSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "toolName": {"type": "string"},
        "ruleContent": {"type": "string", "optional": True},
    },
}

PermissionUpdateSchema: Dict[str, Any] = {
    "type": "discriminatedUnion",
    "discriminant": "type",
    "variants": [
        {
            "type": "object",
            "properties": {
                "type": {"type": "literal", "value": "addRules"},
                "rules": {"type": "array", "items": PermissionRuleValueSchema},
                "behavior": PermissionBehaviorSchema,
                "destination": PermissionUpdateDestinationSchema,
            },
        },
        {
            "type": "object",
            "properties": {
                "type": {"type": "literal", "value": "replaceRules"},
                "rules": {"type": "array", "items": PermissionRuleValueSchema},
                "behavior": PermissionBehaviorSchema,
                "destination": PermissionUpdateDestinationSchema,
            },
        },
        {
            "type": "object",
            "properties": {
                "type": {"type": "literal", "value": "removeRules"},
                "rules": {"type": "array", "items": PermissionRuleValueSchema},
                "behavior": PermissionBehaviorSchema,
                "destination": PermissionUpdateDestinationSchema,
            },
        },
        {
            "type": "object",
            "properties": {
                "type": {"type": "literal", "value": "setMode"},
                "mode": {"$ref": "PermissionModeSchema"},
                "destination": PermissionUpdateDestinationSchema,
            },
        },
        {
            "type": "object",
            "properties": {
                "type": {"type": "literal", "value": "addDirectories"},
                "directories": {"type": "array", "items": {"type": "string"}},
                "destination": PermissionUpdateDestinationSchema,
            },
        },
        {
            "type": "object",
            "properties": {
                "type": {"type": "literal", "value": "removeDirectories"},
                "directories": {"type": "array", "items": {"type": "string"}},
                "destination": PermissionUpdateDestinationSchema,
            },
        },
    ],
}

PermissionDecisionClassificationSchema: Dict[str, Any] = {
    "type": "enum",
    "values": ["user_temporary", "user_permanent", "user_reject"],
    "description": (
        "Classification of this permission decision for telemetry. SDK hosts "
        "that prompt users (desktop apps, IDEs) should set this to reflect "
        "what actually happened: user_temporary for allow-once, user_permanent "
        "for always-allow (both the click and later cache hits), user_reject "
        "for deny. If unset, the CLI infers conservatively (temporary for "
        "allow, reject for deny)."
    ),
}

PermissionResultSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [
        {
            "type": "object",
            "properties": {
                "behavior": {"type": "literal", "value": "allow"},
                "updatedInput": {"type": "record", "optional": True},
                "updatedPermissions": {"type": "array", "optional": True},
                "toolUseID": {"type": "string", "optional": True},
                "decisionClassification": {**PermissionDecisionClassificationSchema, "optional": True},
            },
        },
        {
            "type": "object",
            "properties": {
                "behavior": {"type": "literal", "value": "deny"},
                "message": {"type": "string"},
                "interrupt": {"type": "boolean", "optional": True},
                "toolUseID": {"type": "string", "optional": True},
                "decisionClassification": {**PermissionDecisionClassificationSchema, "optional": True},
            },
        },
    ],
}

PermissionModeSchema: Dict[str, Any] = {
    "type": "enum",
    "values": ["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"],
    "description": (
        "Permission mode for controlling how tool executions are handled. "
        "'default' - Standard behavior, prompts for dangerous operations. "
        "'acceptEdits' - Auto-accept file edit operations. "
        "'bypassPermissions' - Bypass all permission checks (requires allowDangerouslySkipPermissions). "
        "'plan' - Planning mode, no actual tool execution. "
        "'dontAsk' - Don't prompt for permissions, deny if not pre-approved."
    ),
}

PermissionUpdateDestination = Literal["userSettings", "projectSettings", "localSettings", "session", "cliArg"]
PermissionBehavior = Literal["allow", "deny", "ask"]
PermissionDecisionClassification = Literal["user_temporary", "user_permanent", "user_reject"]
PermissionMode = Literal["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"]


class PermissionRuleValue(TypedDict, total=False):
    toolName: str
    ruleContent: str


# ============================================================================
# Hook Types
# ============================================================================

HOOK_EVENTS: Tuple[str, ...] = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "PermissionRequest",
    "PermissionDenied",
    "Setup",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "Elicitation",
    "ElicitationResult",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "InstructionsLoaded",
    "CwdChanged",
    "FileChanged",
)

HookEventSchema: Dict[str, Any] = {"type": "enum", "values": list(HOOK_EVENTS)}

HookEvent = Literal[
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "Notification",
    "UserPromptSubmit", "SessionStart", "SessionEnd", "Stop", "StopFailure",
    "SubagentStart", "SubagentStop", "PreCompact", "PostCompact",
    "PermissionRequest", "PermissionDenied", "Setup", "TeammateIdle",
    "TaskCreated", "TaskCompleted", "Elicitation", "ElicitationResult",
    "ConfigChange", "WorktreeCreate", "WorktreeRemove", "InstructionsLoaded",
    "CwdChanged", "FileChanged",
]

_base_hook_input_props: Dict[str, Any] = {
    "session_id": {"type": "string"},
    "transcript_path": {"type": "string"},
    "cwd": {"type": "string"},
    "permission_mode": {"type": "string", "optional": True},
    "agent_id": {"type": "string", "optional": True},
    "agent_type": {"type": "string", "optional": True},
}

BaseHookInputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": _base_hook_input_props,
}


class BaseHookInput(TypedDict, total=False):
    session_id: str
    transcript_path: str
    cwd: str
    permission_mode: str
    agent_id: str
    agent_type: str


def _hook_schema(event_name: str, extra_props: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to create a hook input schema by extending BaseHookInput."""
    props = dict(_base_hook_input_props)
    props["hook_event_name"] = {"type": "literal", "value": event_name}
    props.update(extra_props)
    return {"type": "object", "properties": props}


PreToolUseHookInputSchema: Dict[str, Any] = _hook_schema("PreToolUse", {
    "tool_name": {"type": "string"},
    "tool_input": {"type": "unknown"},
    "tool_use_id": {"type": "string"},
})

PermissionRequestHookInputSchema: Dict[str, Any] = _hook_schema("PermissionRequest", {
    "tool_name": {"type": "string"},
    "tool_input": {"type": "unknown"},
    "permission_suggestions": {"type": "array", "optional": True},
})

PostToolUseHookInputSchema: Dict[str, Any] = _hook_schema("PostToolUse", {
    "tool_name": {"type": "string"},
    "tool_input": {"type": "unknown"},
    "tool_response": {"type": "unknown"},
    "tool_use_id": {"type": "string"},
})

PostToolUseFailureHookInputSchema: Dict[str, Any] = _hook_schema("PostToolUseFailure", {
    "tool_name": {"type": "string"},
    "tool_input": {"type": "unknown"},
    "tool_use_id": {"type": "string"},
    "error": {"type": "string"},
    "is_interrupt": {"type": "boolean", "optional": True},
})

PermissionDeniedHookInputSchema: Dict[str, Any] = _hook_schema("PermissionDenied", {
    "tool_name": {"type": "string"},
    "tool_input": {"type": "unknown"},
    "tool_use_id": {"type": "string"},
    "reason": {"type": "string"},
})

NotificationHookInputSchema: Dict[str, Any] = _hook_schema("Notification", {
    "message": {"type": "string"},
    "title": {"type": "string", "optional": True},
    "notification_type": {"type": "string"},
})

UserPromptSubmitHookInputSchema: Dict[str, Any] = _hook_schema("UserPromptSubmit", {
    "prompt": {"type": "string"},
})

SessionStartHookInputSchema: Dict[str, Any] = _hook_schema("SessionStart", {
    "source": {"type": "enum", "values": ["startup", "resume", "clear", "compact"]},
    "agent_type": {"type": "string", "optional": True},
    "model": {"type": "string", "optional": True},
})

SetupHookInputSchema: Dict[str, Any] = _hook_schema("Setup", {
    "trigger": {"type": "enum", "values": ["init", "maintenance"]},
})

StopHookInputSchema: Dict[str, Any] = _hook_schema("Stop", {
    "stop_hook_active": {"type": "boolean"},
    "last_assistant_message": {"type": "string", "optional": True},
})

StopFailureHookInputSchema: Dict[str, Any] = _hook_schema("StopFailure", {
    "error": {"$ref": "SDKAssistantMessageErrorSchema"},
    "error_details": {"type": "string", "optional": True},
    "last_assistant_message": {"type": "string", "optional": True},
})

SubagentStartHookInputSchema: Dict[str, Any] = _hook_schema("SubagentStart", {
    "agent_id": {"type": "string"},
    "agent_type": {"type": "string"},
})

SubagentStopHookInputSchema: Dict[str, Any] = _hook_schema("SubagentStop", {
    "stop_hook_active": {"type": "boolean"},
    "agent_id": {"type": "string"},
    "agent_transcript_path": {"type": "string"},
    "agent_type": {"type": "string"},
    "last_assistant_message": {"type": "string", "optional": True},
})

PreCompactHookInputSchema: Dict[str, Any] = _hook_schema("PreCompact", {
    "trigger": {"type": "enum", "values": ["manual", "auto"]},
    "custom_instructions": {"type": "string", "nullable": True},
})

PostCompactHookInputSchema: Dict[str, Any] = _hook_schema("PostCompact", {
    "trigger": {"type": "enum", "values": ["manual", "auto"]},
    "compact_summary": {"type": "string"},
})

TeammateIdleHookInputSchema: Dict[str, Any] = _hook_schema("TeammateIdle", {
    "teammate_name": {"type": "string"},
    "team_name": {"type": "string"},
})

TaskCreatedHookInputSchema: Dict[str, Any] = _hook_schema("TaskCreated", {
    "task_id": {"type": "string"},
    "task_subject": {"type": "string"},
    "task_description": {"type": "string", "optional": True},
    "teammate_name": {"type": "string", "optional": True},
    "team_name": {"type": "string", "optional": True},
})

TaskCompletedHookInputSchema: Dict[str, Any] = _hook_schema("TaskCompleted", {
    "task_id": {"type": "string"},
    "task_subject": {"type": "string"},
    "task_description": {"type": "string", "optional": True},
    "teammate_name": {"type": "string", "optional": True},
    "team_name": {"type": "string", "optional": True},
})

ElicitationHookInputSchema: Dict[str, Any] = {
    **_hook_schema("Elicitation", {
        "mcp_server_name": {"type": "string"},
        "message": {"type": "string"},
        "mode": {"type": "enum", "values": ["form", "url"], "optional": True},
        "url": {"type": "string", "optional": True},
        "elicitation_id": {"type": "string", "optional": True},
        "requested_schema": {"type": "record", "optional": True},
    }),
    "description": "Hook input for the Elicitation event.",
}

ElicitationResultHookInputSchema: Dict[str, Any] = {
    **_hook_schema("ElicitationResult", {
        "mcp_server_name": {"type": "string"},
        "elicitation_id": {"type": "string", "optional": True},
        "mode": {"type": "enum", "values": ["form", "url"], "optional": True},
        "action": {"type": "enum", "values": ["accept", "decline", "cancel"]},
        "content": {"type": "record", "optional": True},
    }),
    "description": "Hook input for the ElicitationResult event.",
}

CONFIG_CHANGE_SOURCES: Tuple[str, ...] = (
    "user_settings",
    "project_settings",
    "local_settings",
    "policy_settings",
    "skills",
)

ConfigChangeHookInputSchema: Dict[str, Any] = _hook_schema("ConfigChange", {
    "source": {"type": "enum", "values": list(CONFIG_CHANGE_SOURCES)},
    "file_path": {"type": "string", "optional": True},
})

INSTRUCTIONS_LOAD_REASONS: Tuple[str, ...] = (
    "session_start",
    "nested_traversal",
    "path_glob_match",
    "include",
    "compact",
)

INSTRUCTIONS_MEMORY_TYPES: Tuple[str, ...] = (
    "User",
    "Project",
    "Local",
    "Managed",
)

InstructionsLoadedHookInputSchema: Dict[str, Any] = _hook_schema("InstructionsLoaded", {
    "file_path": {"type": "string"},
    "memory_type": {"type": "enum", "values": list(INSTRUCTIONS_MEMORY_TYPES)},
    "load_reason": {"type": "enum", "values": list(INSTRUCTIONS_LOAD_REASONS)},
    "globs": {"type": "array", "items": {"type": "string"}, "optional": True},
    "trigger_file_path": {"type": "string", "optional": True},
    "parent_file_path": {"type": "string", "optional": True},
})

WorktreeCreateHookInputSchema: Dict[str, Any] = _hook_schema("WorktreeCreate", {
    "name": {"type": "string"},
})

WorktreeRemoveHookInputSchema: Dict[str, Any] = _hook_schema("WorktreeRemove", {
    "worktree_path": {"type": "string"},
})

CwdChangedHookInputSchema: Dict[str, Any] = _hook_schema("CwdChanged", {
    "old_cwd": {"type": "string"},
    "new_cwd": {"type": "string"},
})

FileChangedHookInputSchema: Dict[str, Any] = _hook_schema("FileChanged", {
    "file_path": {"type": "string"},
    "event": {"type": "enum", "values": ["change", "add", "unlink"]},
})

EXIT_REASONS: Tuple[str, ...] = (
    "clear",
    "resume",
    "logout",
    "prompt_input_exit",
    "other",
    "bypass_permissions_disabled",
)

ExitReasonSchema: Dict[str, Any] = {"type": "enum", "values": list(EXIT_REASONS)}

ExitReason = Literal["clear", "resume", "logout", "prompt_input_exit", "other", "bypass_permissions_disabled"]

SessionEndHookInputSchema: Dict[str, Any] = _hook_schema("SessionEnd", {
    "reason": ExitReasonSchema,
})

HookInputSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [
        PreToolUseHookInputSchema,
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
        PermissionRequestHookInputSchema,
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
    ],
}

# ============================================================================
# Hook Output Types
# ============================================================================

AsyncHookJSONOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "async": {"type": "literal", "value": True},
        "asyncTimeout": {"type": "number", "optional": True},
    },
}

PreToolUseHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "PreToolUse"},
        "permissionDecision": {**PermissionBehaviorSchema, "optional": True},
        "permissionDecisionReason": {"type": "string", "optional": True},
        "updatedInput": {"type": "record", "optional": True},
        "additionalContext": {"type": "string", "optional": True},
    },
}

UserPromptSubmitHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "UserPromptSubmit"},
        "additionalContext": {"type": "string", "optional": True},
    },
}

SessionStartHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "SessionStart"},
        "additionalContext": {"type": "string", "optional": True},
        "initialUserMessage": {"type": "string", "optional": True},
        "watchPaths": {"type": "array", "items": {"type": "string"}, "optional": True},
    },
}

SetupHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "Setup"},
        "additionalContext": {"type": "string", "optional": True},
    },
}

SubagentStartHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "SubagentStart"},
        "additionalContext": {"type": "string", "optional": True},
    },
}

PostToolUseHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "PostToolUse"},
        "additionalContext": {"type": "string", "optional": True},
        "updatedMCPToolOutput": {"type": "unknown", "optional": True},
    },
}

PostToolUseFailureHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "PostToolUseFailure"},
        "additionalContext": {"type": "string", "optional": True},
    },
}

PermissionDeniedHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "PermissionDenied"},
        "retry": {"type": "boolean", "optional": True},
    },
}

NotificationHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "Notification"},
        "additionalContext": {"type": "string", "optional": True},
    },
}

PermissionRequestHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "PermissionRequest"},
        "decision": {
            "type": "union",
            "variants": [
                {
                    "type": "object",
                    "properties": {
                        "behavior": {"type": "literal", "value": "allow"},
                        "updatedInput": {"type": "record", "optional": True},
                        "updatedPermissions": {"type": "array", "optional": True},
                    },
                },
                {
                    "type": "object",
                    "properties": {
                        "behavior": {"type": "literal", "value": "deny"},
                        "message": {"type": "string", "optional": True},
                        "interrupt": {"type": "boolean", "optional": True},
                    },
                },
            ],
        },
    },
}

ElicitationHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Hook-specific output for the Elicitation event.",
    "properties": {
        "hookEventName": {"type": "literal", "value": "Elicitation"},
        "action": {"type": "enum", "values": ["accept", "decline", "cancel"], "optional": True},
        "content": {"type": "record", "optional": True},
    },
}

ElicitationResultHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Hook-specific output for the ElicitationResult event.",
    "properties": {
        "hookEventName": {"type": "literal", "value": "ElicitationResult"},
        "action": {"type": "enum", "values": ["accept", "decline", "cancel"], "optional": True},
        "content": {"type": "record", "optional": True},
    },
}

CwdChangedHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "CwdChanged"},
        "watchPaths": {"type": "array", "items": {"type": "string"}, "optional": True},
    },
}

FileChangedHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "hookEventName": {"type": "literal", "value": "FileChanged"},
        "watchPaths": {"type": "array", "items": {"type": "string"}, "optional": True},
    },
}

WorktreeCreateHookSpecificOutputSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Hook-specific output for the WorktreeCreate event.",
    "properties": {
        "hookEventName": {"type": "literal", "value": "WorktreeCreate"},
        "worktreePath": {"type": "string"},
    },
}

SyncHookJSONOutputSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "continue": {"type": "boolean", "optional": True},
        "suppressOutput": {"type": "boolean", "optional": True},
        "stopReason": {"type": "string", "optional": True},
        "decision": {"type": "enum", "values": ["approve", "block"], "optional": True},
        "systemMessage": {"type": "string", "optional": True},
        "reason": {"type": "string", "optional": True},
        "hookSpecificOutput": {"type": "union", "optional": True, "variants": [
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
            WorktreeCreateHookSpecificOutputSchema,
        ]},
    },
}

HookJSONOutputSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [AsyncHookJSONOutputSchema, SyncHookJSONOutputSchema],
}

# ============================================================================
# Prompt Request/Response Types
# ============================================================================

PromptRequestOptionSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "key": {"type": "string", "description": "Unique key for this option, returned in the response"},
        "label": {"type": "string", "description": "Display text for this option"},
        "description": {"type": "string", "optional": True, "description": "Optional description shown below the label"},
    },
}

PromptRequestSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "Request ID."},
        "message": {"type": "string", "description": "The prompt message to display to the user"},
        "options": {"type": "array", "items": PromptRequestOptionSchema, "description": "Available options for the user to choose from"},
    },
}

PromptResponseSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt_response": {"type": "string", "description": "The request ID from the corresponding prompt request"},
        "selected": {"type": "string", "description": "The key of the selected option"},
    },
}


class PromptRequestOption(TypedDict, total=False):
    key: str
    label: str
    description: str


class PromptRequest(TypedDict):
    prompt: str
    message: str
    options: List[PromptRequestOption]


class PromptResponse(TypedDict):
    prompt_response: str
    selected: str


# ============================================================================
# Skill/Command Types
# ============================================================================

SlashCommandSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Information about an available skill (invoked via /command syntax).",
    "properties": {
        "name": {"type": "string", "description": "Skill name (without the leading slash)"},
        "description": {"type": "string", "description": "Description of what the skill does"},
        "argumentHint": {"type": "string", "description": 'Hint for skill arguments (e.g., "<file>")'},
    },
}

AgentInfoSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Information about an available subagent that can be invoked via the Task tool.",
    "properties": {
        "name": {"type": "string", "description": 'Agent type identifier (e.g., "Explore")'},
        "description": {"type": "string", "description": "Description of when to use this agent"},
        "model": {"type": "string", "optional": True, "description": "Model alias this agent uses."},
    },
}

ModelInfoSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Information about an available model.",
    "properties": {
        "value": {"type": "string", "description": "Model identifier to use in API calls"},
        "displayName": {"type": "string", "description": "Human-readable display name"},
        "description": {"type": "string", "description": "Description of the model's capabilities"},
        "supportsEffort": {"type": "boolean", "optional": True},
        "supportedEffortLevels": {"type": "array", "optional": True},
        "supportsAdaptiveThinking": {"type": "boolean", "optional": True},
        "supportsFastMode": {"type": "boolean", "optional": True},
        "supportsAutoMode": {"type": "boolean", "optional": True},
    },
}

AccountInfoSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Information about the logged in user's account.",
    "properties": {
        "email": {"type": "string", "optional": True},
        "organization": {"type": "string", "optional": True},
        "subscriptionType": {"type": "string", "optional": True},
        "tokenSource": {"type": "string", "optional": True},
        "apiKeySource": {"type": "string", "optional": True},
        "apiProvider": {
            "type": "enum",
            "values": ["firstParty", "bedrock", "vertex", "foundry"],
            "optional": True,
        },
    },
}


class SlashCommand(TypedDict):
    name: str
    description: str
    argumentHint: str


class AgentInfo(TypedDict, total=False):
    name: str
    description: str
    model: str


class ModelInfo(TypedDict, total=False):
    value: str
    displayName: str
    description: str
    supportsEffort: bool
    supportedEffortLevels: List[str]
    supportsAdaptiveThinking: bool
    supportsFastMode: bool
    supportsAutoMode: bool


class AccountInfo(TypedDict, total=False):
    email: str
    organization: str
    subscriptionType: str
    tokenSource: str
    apiKeySource: str
    apiProvider: Literal["firstParty", "bedrock", "vertex", "foundry"]


# ============================================================================
# Agent Definition Types
# ============================================================================

AgentMcpServerSpecSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [
        {"type": "string"},
        {"type": "record", "key": "string", "value": McpServerConfigForProcessTransportSchema},
    ],
}

AgentDefinitionSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Definition for a custom subagent that can be invoked via the Agent tool.",
    "properties": {
        "description": {"type": "string"},
        "tools": {"type": "array", "items": {"type": "string"}, "optional": True},
        "disallowedTools": {"type": "array", "items": {"type": "string"}, "optional": True},
        "prompt": {"type": "string"},
        "model": {"type": "string", "optional": True},
        "mcpServers": {"type": "array", "optional": True},
        "criticalSystemReminder_EXPERIMENTAL": {"type": "string", "optional": True},
        "skills": {"type": "array", "items": {"type": "string"}, "optional": True},
        "initialPrompt": {"type": "string", "optional": True},
        "maxTurns": {"type": "number", "optional": True},
        "background": {"type": "boolean", "optional": True},
        "memory": {"type": "enum", "values": ["user", "project", "local"], "optional": True},
        "effort": {"type": "union", "optional": True},
        "permissionMode": {**PermissionModeSchema, "optional": True},
    },
}


class AgentDefinition(TypedDict, total=False):
    description: str
    tools: List[str]
    disallowedTools: List[str]
    prompt: str
    model: str
    mcpServers: List[Any]
    criticalSystemReminder_EXPERIMENTAL: str
    skills: List[str]
    initialPrompt: str
    maxTurns: int
    background: bool
    memory: Literal["user", "project", "local"]
    effort: Union[Literal["low", "medium", "high", "max"], int]
    permissionMode: PermissionMode


# ============================================================================
# Settings Types
# ============================================================================

SettingSourceSchema: Dict[str, Any] = {
    "type": "enum",
    "values": ["user", "project", "local"],
    "description": (
        "Source for loading filesystem-based settings. "
        "'user' - Global user settings (~/.claude/settings.json). "
        "'project' - Project settings (.claude/settings.json). "
        "'local' - Local settings (.claude/settings.local.json)."
    ),
}

SettingSource = Literal["user", "project", "local"]

SdkPluginConfigSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Configuration for loading a plugin.",
    "properties": {
        "type": {"type": "literal", "value": "local", "description": "Plugin type. Currently only 'local' is supported"},
        "path": {"type": "string", "description": "Absolute or relative path to the plugin directory"},
    },
}


class SdkPluginConfig(TypedDict):
    type: Literal["local"]
    path: str


# ============================================================================
# Rewind Types
# ============================================================================

RewindFilesResultSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Result of a rewindFiles operation.",
    "properties": {
        "canRewind": {"type": "boolean"},
        "error": {"type": "string", "optional": True},
        "filesChanged": {"type": "array", "items": {"type": "string"}, "optional": True},
        "insertions": {"type": "number", "optional": True},
        "deletions": {"type": "number", "optional": True},
    },
}


class RewindFilesResult(TypedDict, total=False):
    canRewind: bool
    error: str
    filesChanged: List[str]
    insertions: int
    deletions: int


# ============================================================================
# External Type Placeholders
# ============================================================================
# These use Any as placeholders for external SDK types.

APIUserMessagePlaceholder = Any  # Placeholder for APIUserMessage from @anthropic-ai/sdk
APIAssistantMessagePlaceholder = Any  # Placeholder for APIAssistantMessage from @anthropic-ai/sdk
RawMessageStreamEventPlaceholder = Any  # Placeholder for RawMessageStreamEvent
UUIDPlaceholder = str  # Placeholder for UUID from crypto
NonNullableUsagePlaceholder = Any  # Placeholder for NonNullableUsage

# ============================================================================
# SDK Message Types
# ============================================================================

SDKAssistantMessageErrorSchema: Dict[str, Any] = {
    "type": "enum",
    "values": [
        "authentication_failed",
        "billing_error",
        "rate_limit",
        "invalid_request",
        "server_error",
        "unknown",
        "max_output_tokens",
    ],
}

SDKAssistantMessageError = Literal[
    "authentication_failed", "billing_error", "rate_limit",
    "invalid_request", "server_error", "unknown", "max_output_tokens"
]

SDKStatusSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [{"type": "literal", "value": "compacting"}, {"type": "null"}],
}

FastModeStateSchema: Dict[str, Any] = {
    "type": "enum",
    "values": ["off", "cooldown", "on"],
    "description": "Fast mode state: off, in cooldown after rate limit, or actively enabled.",
}

FastModeState = Literal["off", "cooldown", "on"]

SDKUserMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "user"},
        "message": {"type": "unknown"},  # APIUserMessage placeholder
        "parent_tool_use_id": {"type": "string", "nullable": True},
        "isSynthetic": {"type": "boolean", "optional": True},
        "tool_use_result": {"type": "unknown", "optional": True},
        "priority": {"type": "enum", "values": ["now", "next", "later"], "optional": True},
        "timestamp": {"type": "string", "optional": True},
        "uuid": {"type": "string", "optional": True},
        "session_id": {"type": "string", "optional": True},
    },
}

SDKUserMessageReplaySchema: Dict[str, Any] = {
    **SDKUserMessageSchema,
    "properties": {
        **SDKUserMessageSchema["properties"],
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
        "isReplay": {"type": "literal", "value": True},
    },
}

SDKRateLimitInfoSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Rate limit information for claude.ai subscription users.",
    "properties": {
        "status": {"type": "enum", "values": ["allowed", "allowed_warning", "rejected"]},
        "resetsAt": {"type": "number", "optional": True},
        "rateLimitType": {"type": "enum", "optional": True},
        "utilization": {"type": "number", "optional": True},
        "overageStatus": {"type": "enum", "optional": True},
        "overageResetsAt": {"type": "number", "optional": True},
        "overageDisabledReason": {"type": "enum", "optional": True},
        "isUsingOverage": {"type": "boolean", "optional": True},
        "surpassedThreshold": {"type": "number", "optional": True},
    },
}

SDKAssistantMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "assistant"},
        "message": {"type": "unknown"},
        "parent_tool_use_id": {"type": "string", "nullable": True},
        "error": {**SDKAssistantMessageErrorSchema, "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKRateLimitEventSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Rate limit event emitted when rate limit info changes.",
    "properties": {
        "type": {"type": "literal", "value": "rate_limit_event"},
        "rate_limit_info": SDKRateLimitInfoSchema,
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKStreamlinedTextMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "@internal Streamlined text message.",
    "properties": {
        "type": {"type": "literal", "value": "streamlined_text"},
        "text": {"type": "string"},
        "session_id": {"type": "string"},
        "uuid": {"type": "string"},
    },
}

SDKStreamlinedToolUseSummaryMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "@internal Streamlined tool use summary.",
    "properties": {
        "type": {"type": "literal", "value": "streamlined_tool_use_summary"},
        "tool_summary": {"type": "string"},
        "session_id": {"type": "string"},
        "uuid": {"type": "string"},
    },
}

SDKPermissionDenialSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "tool_name": {"type": "string"},
        "tool_use_id": {"type": "string"},
        "tool_input": {"type": "record"},
    },
}

SDKResultSuccessSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "result"},
        "subtype": {"type": "literal", "value": "success"},
        "duration_ms": {"type": "number"},
        "duration_api_ms": {"type": "number"},
        "is_error": {"type": "boolean"},
        "num_turns": {"type": "number"},
        "result": {"type": "string"},
        "stop_reason": {"type": "string", "nullable": True},
        "total_cost_usd": {"type": "number"},
        "usage": {"type": "unknown"},
        "modelUsage": {"type": "record"},
        "permission_denials": {"type": "array"},
        "structured_output": {"type": "unknown", "optional": True},
        "fast_mode_state": {**FastModeStateSchema, "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKResultErrorSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "result"},
        "subtype": {
            "type": "enum",
            "values": [
                "error_during_execution",
                "error_max_turns",
                "error_max_budget_usd",
                "error_max_structured_output_retries",
            ],
        },
        "duration_ms": {"type": "number"},
        "duration_api_ms": {"type": "number"},
        "is_error": {"type": "boolean"},
        "num_turns": {"type": "number"},
        "stop_reason": {"type": "string", "nullable": True},
        "total_cost_usd": {"type": "number"},
        "usage": {"type": "unknown"},
        "modelUsage": {"type": "record"},
        "permission_denials": {"type": "array"},
        "errors": {"type": "array", "items": {"type": "string"}},
        "fast_mode_state": {**FastModeStateSchema, "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKResultMessageSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [SDKResultSuccessSchema, SDKResultErrorSchema],
}

SDKSystemMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "init"},
        "agents": {"type": "array", "optional": True},
        "apiKeySource": ApiKeySourceSchema,
        "betas": {"type": "array", "optional": True},
        "claude_code_version": {"type": "string"},
        "cwd": {"type": "string"},
        "tools": {"type": "array"},
        "mcp_servers": {"type": "array"},
        "model": {"type": "string"},
        "permissionMode": PermissionModeSchema,
        "slash_commands": {"type": "array"},
        "output_style": {"type": "string"},
        "skills": {"type": "array"},
        "plugins": {"type": "array"},
        "fast_mode_state": {**FastModeStateSchema, "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKPartialAssistantMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "stream_event"},
        "event": {"type": "unknown"},
        "parent_tool_use_id": {"type": "string", "nullable": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKCompactBoundaryMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "compact_boundary"},
        "compact_metadata": {"type": "object"},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKStatusMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "status"},
        "status": SDKStatusSchema,
        "permissionMode": {**PermissionModeSchema, "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKPostTurnSummaryMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "@internal Background post-turn summary.",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "post_turn_summary"},
        "summarizes_uuid": {"type": "string"},
        "status_category": {"type": "enum", "values": ["blocked", "waiting", "completed", "review_ready", "failed"]},
        "status_detail": {"type": "string"},
        "is_noteworthy": {"type": "boolean"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "recent_action": {"type": "string"},
        "needs_action": {"type": "string"},
        "artifact_urls": {"type": "array"},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKAPIRetryMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Emitted when an API request fails with a retryable error.",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "api_retry"},
        "attempt": {"type": "number"},
        "max_retries": {"type": "number"},
        "retry_delay_ms": {"type": "number"},
        "error_status": {"type": "number", "nullable": True},
        "error": SDKAssistantMessageErrorSchema,
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKLocalCommandOutputMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Output from a local slash command.",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "local_command_output"},
        "content": {"type": "string"},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKHookStartedMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "hook_started"},
        "hook_id": {"type": "string"},
        "hook_name": {"type": "string"},
        "hook_event": {"type": "string"},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKHookProgressMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "hook_progress"},
        "hook_id": {"type": "string"},
        "hook_name": {"type": "string"},
        "hook_event": {"type": "string"},
        "stdout": {"type": "string"},
        "stderr": {"type": "string"},
        "output": {"type": "string"},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKHookResponseMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "hook_response"},
        "hook_id": {"type": "string"},
        "hook_name": {"type": "string"},
        "hook_event": {"type": "string"},
        "output": {"type": "string"},
        "stdout": {"type": "string"},
        "stderr": {"type": "string"},
        "exit_code": {"type": "number", "optional": True},
        "outcome": {"type": "enum", "values": ["success", "error", "cancelled"]},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKToolProgressMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "tool_progress"},
        "tool_use_id": {"type": "string"},
        "tool_name": {"type": "string"},
        "parent_tool_use_id": {"type": "string", "nullable": True},
        "elapsed_time_seconds": {"type": "number"},
        "task_id": {"type": "string", "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKAuthStatusMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "auth_status"},
        "isAuthenticating": {"type": "boolean"},
        "output": {"type": "array", "items": {"type": "string"}},
        "error": {"type": "string", "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKFilesPersistedEventSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "files_persisted"},
        "files": {"type": "array"},
        "failed": {"type": "array"},
        "processed_at": {"type": "string"},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKTaskNotificationMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "task_notification"},
        "task_id": {"type": "string"},
        "tool_use_id": {"type": "string", "optional": True},
        "status": {"type": "enum", "values": ["completed", "failed", "stopped"]},
        "output_file": {"type": "string"},
        "summary": {"type": "string"},
        "usage": {"type": "object", "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKTaskStartedMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "task_started"},
        "task_id": {"type": "string"},
        "tool_use_id": {"type": "string", "optional": True},
        "description": {"type": "string"},
        "task_type": {"type": "string", "optional": True},
        "workflow_name": {"type": "string", "optional": True},
        "prompt": {"type": "string", "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKSessionStateChangedMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Mirrors notifySessionStateChanged.",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "session_state_changed"},
        "state": {"type": "enum", "values": ["idle", "running", "requires_action"]},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKTaskProgressMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "task_progress"},
        "task_id": {"type": "string"},
        "tool_use_id": {"type": "string", "optional": True},
        "description": {"type": "string"},
        "usage": {"type": "object"},
        "last_tool_name": {"type": "string", "optional": True},
        "summary": {"type": "string", "optional": True},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKToolUseSummaryMessageSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "tool_use_summary"},
        "summary": {"type": "string"},
        "preceding_tool_use_ids": {"type": "array", "items": {"type": "string"}},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKElicitationCompleteMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Emitted when an MCP server confirms that a URL-mode elicitation is complete.",
    "properties": {
        "type": {"type": "literal", "value": "system"},
        "subtype": {"type": "literal", "value": "elicitation_complete"},
        "mcp_server_name": {"type": "string"},
        "elicitation_id": {"type": "string"},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

SDKPromptSuggestionMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Predicted next user prompt, emitted after each turn when promptSuggestions is enabled.",
    "properties": {
        "type": {"type": "literal", "value": "prompt_suggestion"},
        "suggestion": {"type": "string"},
        "uuid": {"type": "string"},
        "session_id": {"type": "string"},
    },
}

# ============================================================================
# Session Listing Types
# ============================================================================

SDKSessionInfoSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Session metadata returned by listSessions and getSessionInfo.",
    "properties": {
        "sessionId": {"type": "string", "description": "Unique session identifier (UUID)."},
        "summary": {"type": "string"},
        "lastModified": {"type": "number"},
        "fileSize": {"type": "number", "optional": True},
        "customTitle": {"type": "string", "optional": True},
        "firstPrompt": {"type": "string", "optional": True},
        "gitBranch": {"type": "string", "optional": True},
        "cwd": {"type": "string", "optional": True},
        "tag": {"type": "string", "optional": True},
        "createdAt": {"type": "number", "optional": True},
    },
}


class SDKSessionInfo(TypedDict, total=False):
    sessionId: str
    summary: str
    lastModified: int
    fileSize: int
    customTitle: str
    firstPrompt: str
    gitBranch: str
    cwd: str
    tag: str
    createdAt: int


SDKMessageSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [
        SDKAssistantMessageSchema,
        SDKUserMessageSchema,
        SDKUserMessageReplaySchema,
        SDKResultMessageSchema,
        SDKSystemMessageSchema,
        SDKPartialAssistantMessageSchema,
        SDKCompactBoundaryMessageSchema,
        SDKStatusMessageSchema,
        SDKAPIRetryMessageSchema,
        SDKLocalCommandOutputMessageSchema,
        SDKHookStartedMessageSchema,
        SDKHookProgressMessageSchema,
        SDKHookResponseMessageSchema,
        SDKToolProgressMessageSchema,
        SDKAuthStatusMessageSchema,
        SDKTaskNotificationMessageSchema,
        SDKTaskStartedMessageSchema,
        SDKTaskProgressMessageSchema,
        SDKSessionStateChangedMessageSchema,
        SDKFilesPersistedEventSchema,
        SDKToolUseSummaryMessageSchema,
        SDKRateLimitEventSchema,
        SDKElicitationCompleteMessageSchema,
        SDKPromptSuggestionMessageSchema,
    ],
}
