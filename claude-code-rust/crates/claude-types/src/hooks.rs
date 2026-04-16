// Original TS source: types/hooks.ts
// Hook result and callback types

use serde::{Deserialize, Serialize};
use crate::permissions::PermissionUpdate;
use crate::message::Message;
use crate::command::HookBlockingError;

pub use crate::command::{HookEvent, HookDecision, SyncHookResponse, AsyncHookResponse, HookSpecificOutput, HookProgress};

/// Permission request result
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "behavior", rename_all = "lowercase")]
pub enum PermissionRequestResult {
    Allow {
        updated_input: Option<std::collections::HashMap<String, serde_json::Value>>,
        updated_permissions: Option<Vec<PermissionUpdate>>,
    },
    Deny {
        message: Option<String>,
        interrupt: Option<bool>,
    },
}

/// Result from a hook execution
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HookResult {
    pub message: Option<Message>,
    pub system_message: Option<Message>,
    pub blocking_error: Option<HookBlockingError>,
    pub outcome: HookOutcome,
    pub prevent_continuation: Option<bool>,
    pub stop_reason: Option<String>,
    pub permission_behavior: Option<String>, // "ask" | "deny" | "allow" | "passthrough"
    pub hook_permission_decision_reason: Option<String>,
    pub additional_context: Option<String>,
    pub initial_user_message: Option<String>,
    pub updated_input: Option<std::collections::HashMap<String, serde_json::Value>>,
    pub updated_mcp_tool_output: Option<serde_json::Value>,
    pub permission_request_result: Option<PermissionRequestResult>,
    pub retry: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HookOutcome {
    Success,
    Blocking,
    NonBlockingError,
    Cancelled,
}

/// Aggregated result from multiple hooks
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AggregatedHookResult {
    pub message: Option<Message>,
    pub blocking_errors: Option<Vec<HookBlockingError>>,
    pub prevent_continuation: Option<bool>,
    pub stop_reason: Option<String>,
    pub hook_permission_decision_reason: Option<String>,
    pub permission_behavior: Option<String>,
    pub additional_contexts: Option<Vec<String>>,
    pub initial_user_message: Option<String>,
    pub updated_input: Option<std::collections::HashMap<String, serde_json::Value>>,
    pub updated_mcp_tool_output: Option<serde_json::Value>,
    pub permission_request_result: Option<PermissionRequestResult>,
    pub retry: Option<bool>,
}

/// Prompt request for elicitation protocol
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PromptRequest {
    pub prompt: String, // request id
    pub message: String,
    pub options: Vec<PromptOption>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PromptOption {
    pub key: String,
    pub label: String,
    pub description: Option<String>,
}

/// Prompt response
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct PromptResponse {
    pub prompt_response: String, // request id
    pub selected: String,
}
