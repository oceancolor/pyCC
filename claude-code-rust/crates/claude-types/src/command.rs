// Original TS source: types/command.ts (inferred), types/hooks.ts
// Command and hook types

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Base command definition
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CommandDefinition {
    pub name: String,
    pub description: String,
    pub aliases: Option<Vec<String>>,
}

/// Hook event types
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "PascalCase")]
pub enum HookEvent {
    PreToolUse,
    PostToolUse,
    PostToolUseFailure,
    UserPromptSubmit,
    SessionStart,
    Setup,
    SubagentStart,
    PermissionDenied,
    Notification,
    PermissionRequest,
    Elicitation,
    ElicitationResult,
    CwdChanged,
    FileChanged,
    WorktreeCreate,
}

pub const HOOK_EVENTS: &[HookEvent] = &[
    HookEvent::PreToolUse,
    HookEvent::PostToolUse,
    HookEvent::PostToolUseFailure,
    HookEvent::UserPromptSubmit,
    HookEvent::SessionStart,
    HookEvent::Setup,
    HookEvent::SubagentStart,
    HookEvent::PermissionDenied,
    HookEvent::Notification,
    HookEvent::PermissionRequest,
    HookEvent::Elicitation,
    HookEvent::ElicitationResult,
    HookEvent::CwdChanged,
    HookEvent::FileChanged,
    HookEvent::WorktreeCreate,
];

/// Sync hook response
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncHookResponse {
    #[serde(rename = "continue")]
    pub should_continue: Option<bool>,
    pub suppress_output: Option<bool>,
    pub stop_reason: Option<String>,
    pub decision: Option<HookDecision>,
    pub reason: Option<String>,
    pub system_message: Option<String>,
    pub hook_specific_output: Option<HookSpecificOutput>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum HookDecision {
    Approve,
    Block,
}

/// Async hook response
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AsyncHookResponse {
    #[serde(rename = "async")]
    pub is_async: bool, // always true
    pub async_timeout: Option<u64>,
}

/// Hook-specific output for various event types
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "hookEventName")]
pub enum HookSpecificOutput {
    PreToolUse {
        permission_decision: Option<Value>,
        permission_decision_reason: Option<String>,
        updated_input: Option<std::collections::HashMap<String, Value>>,
        additional_context: Option<String>,
    },
    UserPromptSubmit {
        additional_context: Option<String>,
    },
    SessionStart {
        additional_context: Option<String>,
        initial_user_message: Option<String>,
        watch_paths: Option<Vec<String>>,
    },
    Setup {
        additional_context: Option<String>,
    },
    SubagentStart {
        additional_context: Option<String>,
    },
    PostToolUse {
        additional_context: Option<String>,
        updated_mcp_tool_output: Option<Value>,
    },
    PostToolUseFailure {
        additional_context: Option<String>,
    },
    PermissionDenied {
        retry: Option<bool>,
    },
    Notification {
        additional_context: Option<String>,
    },
    PermissionRequest {
        decision: PermissionRequestDecision,
    },
    Elicitation {
        action: Option<ElicitationAction>,
        content: Option<std::collections::HashMap<String, Value>>,
    },
    ElicitationResult {
        action: Option<ElicitationAction>,
        content: Option<std::collections::HashMap<String, Value>>,
    },
    CwdChanged {
        watch_paths: Option<Vec<String>>,
    },
    FileChanged {
        watch_paths: Option<Vec<String>>,
    },
    WorktreeCreate {
        worktree_path: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "behavior", rename_all = "lowercase")]
pub enum PermissionRequestDecision {
    Allow {
        updated_input: Option<std::collections::HashMap<String, Value>>,
        updated_permissions: Option<Vec<crate::permissions::PermissionUpdate>>,
    },
    Deny {
        message: Option<String>,
        interrupt: Option<bool>,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ElicitationAction {
    Accept,
    Decline,
    Cancel,
}

/// Hook progress event
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HookProgress {
    #[serde(rename = "type")]
    pub event_type: String, // "hook_progress"
    pub hook_event: HookEvent,
    pub hook_name: String,
    pub command: String,
    pub prompt_text: Option<String>,
    pub status_message: Option<String>,
}

/// Hook blocking error
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HookBlockingError {
    pub blocking_error: String,
    pub command: String,
}
