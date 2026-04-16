"""
SDK Control Schemas - Schema descriptions for the control protocol.

These schemas define the control protocol between SDK implementations and the CLI.
Used by SDK builders (e.g., Python SDK) to communicate with the CLI process.

SDK consumers should use core_schemas.py instead.

Corresponds to sdk/controlSchemas.ts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from typing import TypedDict

from claude_code.entrypoints.sdk.core_schemas import (
    AccountInfoSchema,
    AgentDefinitionSchema,
    AgentInfoSchema,
    FastModeStateSchema,
    HookEventSchema,
    HookInputSchema,
    McpServerConfigForProcessTransportSchema,
    McpServerStatusSchema,
    ModelInfoSchema,
    PermissionModeSchema,
    PermissionUpdateSchema,
    SDKMessageSchema,
    SDKPostTurnSummaryMessageSchema,
    SDKStreamlinedTextMessageSchema,
    SDKStreamlinedToolUseSummaryMessageSchema,
    SDKUserMessageSchema,
    SlashCommandSchema,
)

# ============================================================================
# External Type Placeholders
# ============================================================================

# JSONRPCMessage from @modelcontextprotocol/sdk - treat as unknown
JSONRPCMessagePlaceholder: Dict[str, Any] = {"type": "unknown"}

# ============================================================================
# Hook Callback Types
# ============================================================================

SDKHookCallbackMatcherSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Configuration for matching and routing hook callbacks.",
    "properties": {
        "matcher": {"type": "string", "optional": True},
        "hookCallbackIds": {"type": "array", "items": {"type": "string"}},
        "timeout": {"type": "number", "optional": True},
    },
}


class SDKHookCallbackMatcher(TypedDict, total=False):
    matcher: str
    hookCallbackIds: List[str]
    timeout: int


# ============================================================================
# Control Request Types
# ============================================================================

SDKControlInitializeRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Initializes the SDK session with hooks, MCP servers, and agent configuration.",
    "properties": {
        "subtype": {"type": "literal", "value": "initialize"},
        "hooks": {"type": "record", "key": HookEventSchema["values"], "value": {"type": "array"}, "optional": True},
        "sdkMcpServers": {"type": "array", "items": {"type": "string"}, "optional": True},
        "jsonSchema": {"type": "record", "optional": True},
        "systemPrompt": {"type": "string", "optional": True},
        "appendSystemPrompt": {"type": "string", "optional": True},
        "agents": {"type": "record", "optional": True},
        "promptSuggestions": {"type": "boolean", "optional": True},
        "agentProgressSummaries": {"type": "boolean", "optional": True},
    },
}

SDKControlInitializeResponseSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Response from session initialization with available commands, models, and account info.",
    "properties": {
        "commands": {"type": "array", "items": SlashCommandSchema},
        "agents": {"type": "array", "items": AgentInfoSchema},
        "output_style": {"type": "string"},
        "available_output_styles": {"type": "array", "items": {"type": "string"}},
        "models": {"type": "array", "items": ModelInfoSchema},
        "account": AccountInfoSchema,
        "pid": {"type": "number", "optional": True},
        "fast_mode_state": {**FastModeStateSchema, "optional": True},
    },
}

SDKControlInterruptRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Interrupts the currently running conversation turn.",
    "properties": {
        "subtype": {"type": "literal", "value": "interrupt"},
    },
}

SDKControlPermissionRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Requests permission to use a tool with the given input.",
    "properties": {
        "subtype": {"type": "literal", "value": "can_use_tool"},
        "tool_name": {"type": "string"},
        "input": {"type": "record"},
        "permission_suggestions": {"type": "array", "optional": True},
        "blocked_path": {"type": "string", "optional": True},
        "decision_reason": {"type": "string", "optional": True},
        "title": {"type": "string", "optional": True},
        "display_name": {"type": "string", "optional": True},
        "tool_use_id": {"type": "string"},
        "agent_id": {"type": "string", "optional": True},
        "description": {"type": "string", "optional": True},
    },
}

SDKControlSetPermissionModeRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Sets the permission mode for tool execution handling.",
    "properties": {
        "subtype": {"type": "literal", "value": "set_permission_mode"},
        "mode": PermissionModeSchema,
        "ultraplan": {"type": "boolean", "optional": True},
    },
}

SDKControlSetModelRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Sets the model to use for subsequent conversation turns.",
    "properties": {
        "subtype": {"type": "literal", "value": "set_model"},
        "model": {"type": "string", "optional": True},
    },
}

SDKControlSetMaxThinkingTokensRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Sets the maximum number of thinking tokens for extended thinking.",
    "properties": {
        "subtype": {"type": "literal", "value": "set_max_thinking_tokens"},
        "max_thinking_tokens": {"type": "number", "nullable": True},
    },
}

SDKControlMcpStatusRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Requests the current status of all MCP server connections.",
    "properties": {
        "subtype": {"type": "literal", "value": "mcp_status"},
    },
}

SDKControlMcpStatusResponseSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Response containing the current status of all MCP server connections.",
    "properties": {
        "mcpServers": {"type": "array", "items": McpServerStatusSchema},
    },
}

SDKControlGetContextUsageRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Requests a breakdown of current context window usage by category.",
    "properties": {
        "subtype": {"type": "literal", "value": "get_context_usage"},
    },
}

_ContextCategorySchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "tokens": {"type": "number"},
        "color": {"type": "string"},
        "isDeferred": {"type": "boolean", "optional": True},
    },
}

_ContextGridSquareSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "color": {"type": "string"},
        "isFilled": {"type": "boolean"},
        "categoryName": {"type": "string"},
        "tokens": {"type": "number"},
        "percentage": {"type": "number"},
        "squareFullness": {"type": "number"},
    },
}

SDKControlGetContextUsageResponseSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Breakdown of current context window usage by category.",
    "properties": {
        "categories": {"type": "array", "items": _ContextCategorySchema},
        "totalTokens": {"type": "number"},
        "maxTokens": {"type": "number"},
        "rawMaxTokens": {"type": "number"},
        "percentage": {"type": "number"},
        "gridRows": {"type": "array"},
        "model": {"type": "string"},
        "memoryFiles": {"type": "array"},
        "mcpTools": {"type": "array"},
        "deferredBuiltinTools": {"type": "array", "optional": True},
        "systemTools": {"type": "array", "optional": True},
        "systemPromptSections": {"type": "array", "optional": True},
        "agents": {"type": "array"},
        "slashCommands": {"type": "object", "optional": True},
        "skills": {"type": "object", "optional": True},
        "autoCompactThreshold": {"type": "number", "optional": True},
        "isAutoCompactEnabled": {"type": "boolean"},
        "messageBreakdown": {"type": "object", "optional": True},
        "apiUsage": {"type": "object", "optional": True, "nullable": True},
    },
}

SDKControlRewindFilesRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Rewinds file changes made since a specific user message.",
    "properties": {
        "subtype": {"type": "literal", "value": "rewind_files"},
        "user_message_id": {"type": "string"},
        "dry_run": {"type": "boolean", "optional": True},
    },
}

SDKControlRewindFilesResponseSchema: Dict[str, Any] = {
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

SDKControlCancelAsyncMessageRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Drops a pending async user message from the command queue by uuid.",
    "properties": {
        "subtype": {"type": "literal", "value": "cancel_async_message"},
        "message_uuid": {"type": "string"},
    },
}

SDKControlCancelAsyncMessageResponseSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Result of a cancel_async_message operation.",
    "properties": {
        "cancelled": {"type": "boolean"},
    },
}

SDKControlSeedReadStateRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Seeds the readFileState cache with a path+mtime entry.",
    "properties": {
        "subtype": {"type": "literal", "value": "seed_read_state"},
        "path": {"type": "string"},
        "mtime": {"type": "number"},
    },
}

SDKHookCallbackRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Delivers a hook callback with its input data.",
    "properties": {
        "subtype": {"type": "literal", "value": "hook_callback"},
        "callback_id": {"type": "string"},
        "input": HookInputSchema,
        "tool_use_id": {"type": "string", "optional": True},
    },
}

SDKControlMcpMessageRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Sends a JSON-RPC message to a specific MCP server.",
    "properties": {
        "subtype": {"type": "literal", "value": "mcp_message"},
        "server_name": {"type": "string"},
        "message": JSONRPCMessagePlaceholder,
    },
}

SDKControlMcpSetServersRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Replaces the set of dynamically managed MCP servers.",
    "properties": {
        "subtype": {"type": "literal", "value": "mcp_set_servers"},
        "servers": {"type": "record", "key": "string", "value": McpServerConfigForProcessTransportSchema},
    },
}

SDKControlMcpSetServersResponseSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Result of replacing the set of dynamically managed MCP servers.",
    "properties": {
        "added": {"type": "array", "items": {"type": "string"}},
        "removed": {"type": "array", "items": {"type": "string"}},
        "errors": {"type": "record", "key": "string", "value": "string"},
    },
}

SDKControlReloadPluginsRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Reloads plugins from disk and returns the refreshed session components.",
    "properties": {
        "subtype": {"type": "literal", "value": "reload_plugins"},
    },
}

SDKControlReloadPluginsResponseSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Refreshed commands, agents, plugins, and MCP server status after reload.",
    "properties": {
        "commands": {"type": "array", "items": SlashCommandSchema},
        "agents": {"type": "array", "items": AgentInfoSchema},
        "plugins": {"type": "array"},
        "mcpServers": {"type": "array", "items": McpServerStatusSchema},
        "error_count": {"type": "number"},
    },
}

SDKControlMcpReconnectRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Reconnects a disconnected or failed MCP server.",
    "properties": {
        "subtype": {"type": "literal", "value": "mcp_reconnect"},
        "serverName": {"type": "string"},
    },
}

SDKControlMcpToggleRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Enables or disables an MCP server.",
    "properties": {
        "subtype": {"type": "literal", "value": "mcp_toggle"},
        "serverName": {"type": "string"},
        "enabled": {"type": "boolean"},
    },
}

SDKControlStopTaskRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Stops a running task.",
    "properties": {
        "subtype": {"type": "literal", "value": "stop_task"},
        "task_id": {"type": "string"},
    },
}

SDKControlApplyFlagSettingsRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Merges the provided settings into the flag settings layer.",
    "properties": {
        "subtype": {"type": "literal", "value": "apply_flag_settings"},
        "settings": {"type": "record"},
    },
}

SDKControlGetSettingsRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Returns the effective merged settings and the raw per-source settings.",
    "properties": {
        "subtype": {"type": "literal", "value": "get_settings"},
    },
}

SDKControlGetSettingsResponseSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Effective merged settings plus raw per-source settings in merge order.",
    "properties": {
        "effective": {"type": "record"},
        "sources": {
            "type": "array",
            "description": "Ordered low-to-high priority.",
            "items": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "enum",
                        "values": [
                            "userSettings",
                            "projectSettings",
                            "localSettings",
                            "flagSettings",
                            "policySettings",
                        ],
                    },
                    "settings": {"type": "record"},
                },
            },
        },
        "applied": {
            "type": "object",
            "optional": True,
            "description": "Runtime-resolved values after env overrides.",
            "properties": {
                "model": {"type": "string"},
                "effort": {"type": "enum", "values": ["low", "medium", "high", "max"], "nullable": True},
            },
        },
    },
}

SDKControlElicitationRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Requests the SDK consumer to handle an MCP elicitation (user input request).",
    "properties": {
        "subtype": {"type": "literal", "value": "elicitation"},
        "mcp_server_name": {"type": "string"},
        "message": {"type": "string"},
        "mode": {"type": "enum", "values": ["form", "url"], "optional": True},
        "url": {"type": "string", "optional": True},
        "elicitation_id": {"type": "string", "optional": True},
        "requested_schema": {"type": "record", "optional": True},
    },
}

SDKControlElicitationResponseSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Response from the SDK consumer for an elicitation request.",
    "properties": {
        "action": {"type": "enum", "values": ["accept", "decline", "cancel"]},
        "content": {"type": "record", "optional": True},
    },
}

# ============================================================================
# Control Request/Response Wrappers
# ============================================================================

SDKControlRequestInnerSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [
        SDKControlInterruptRequestSchema,
        SDKControlPermissionRequestSchema,
        SDKControlInitializeRequestSchema,
        SDKControlSetPermissionModeRequestSchema,
        SDKControlSetModelRequestSchema,
        SDKControlSetMaxThinkingTokensRequestSchema,
        SDKControlMcpStatusRequestSchema,
        SDKControlGetContextUsageRequestSchema,
        SDKHookCallbackRequestSchema,
        SDKControlMcpMessageRequestSchema,
        SDKControlRewindFilesRequestSchema,
        SDKControlCancelAsyncMessageRequestSchema,
        SDKControlSeedReadStateRequestSchema,
        SDKControlMcpSetServersRequestSchema,
        SDKControlReloadPluginsRequestSchema,
        SDKControlMcpReconnectRequestSchema,
        SDKControlMcpToggleRequestSchema,
        SDKControlStopTaskRequestSchema,
        SDKControlApplyFlagSettingsRequestSchema,
        SDKControlGetSettingsRequestSchema,
        SDKControlElicitationRequestSchema,
    ],
}

SDKControlRequestSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "control_request"},
        "request_id": {"type": "string"},
        "request": SDKControlRequestInnerSchema,
    },
}

ControlResponseSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "subtype": {"type": "literal", "value": "success"},
        "request_id": {"type": "string"},
        "response": {"type": "record", "optional": True},
    },
}

ControlErrorResponseSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "subtype": {"type": "literal", "value": "error"},
        "request_id": {"type": "string"},
        "error": {"type": "string"},
        "pending_permission_requests": {"type": "array", "optional": True},
    },
}

SDKControlResponseSchema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "literal", "value": "control_response"},
        "response": {
            "type": "union",
            "variants": [ControlResponseSchema, ControlErrorResponseSchema],
        },
    },
}

SDKControlCancelRequestSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Cancels a currently open control request.",
    "properties": {
        "type": {"type": "literal", "value": "control_cancel_request"},
        "request_id": {"type": "string"},
    },
}

SDKKeepAliveMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Keep-alive message to maintain WebSocket connection.",
    "properties": {
        "type": {"type": "literal", "value": "keep_alive"},
    },
}

SDKUpdateEnvironmentVariablesMessageSchema: Dict[str, Any] = {
    "type": "object",
    "description": "Updates environment variables at runtime.",
    "properties": {
        "type": {"type": "literal", "value": "update_environment_variables"},
        "variables": {"type": "record", "key": "string", "value": "string"},
    },
}

# ============================================================================
# Aggregate Message Types
# ============================================================================

StdoutMessageSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [
        SDKMessageSchema,
        SDKStreamlinedTextMessageSchema,
        SDKStreamlinedToolUseSummaryMessageSchema,
        SDKPostTurnSummaryMessageSchema,
        SDKControlResponseSchema,
        SDKControlRequestSchema,
        SDKControlCancelRequestSchema,
        SDKKeepAliveMessageSchema,
    ],
}

StdinMessageSchema: Dict[str, Any] = {
    "type": "union",
    "variants": [
        SDKUserMessageSchema,
        SDKControlRequestSchema,
        SDKControlResponseSchema,
        SDKKeepAliveMessageSchema,
        SDKUpdateEnvironmentVariablesMessageSchema,
    ],
}


# ============================================================================
# TypedDict types
# ============================================================================


class SDKControlRequest(TypedDict):
    type: Literal["control_request"]
    request_id: str
    request: Dict[str, Any]


class ControlResponse(TypedDict, total=False):
    subtype: Literal["success"]
    request_id: str
    response: Dict[str, Any]


class ControlErrorResponse(TypedDict, total=False):
    subtype: Literal["error"]
    request_id: str
    error: str
    pending_permission_requests: List[Dict[str, Any]]


class SDKControlResponse(TypedDict):
    type: Literal["control_response"]
    response: Union[ControlResponse, ControlErrorResponse]


class SDKControlCancelRequest(TypedDict):
    type: Literal["control_cancel_request"]
    request_id: str


class SDKKeepAliveMessage(TypedDict):
    type: Literal["keep_alive"]


class SDKUpdateEnvironmentVariablesMessage(TypedDict):
    type: Literal["update_environment_variables"]
    variables: Dict[str, str]
