// Original TS source: types/permissions.ts
// Permission types - modes, behaviors, rules, decisions

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use serde_json::Value;

// ============================================================================
// Permission Modes
// ============================================================================

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum ExternalPermissionMode {
    AcceptEdits,
    BypassPermissions,
    Default,
    DontAsk,
    Plan,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum PermissionMode {
    AcceptEdits,
    BypassPermissions,
    Default,
    DontAsk,
    Plan,
    Auto,
    Bubble,
}

impl From<ExternalPermissionMode> for PermissionMode {
    fn from(m: ExternalPermissionMode) -> Self {
        match m {
            ExternalPermissionMode::AcceptEdits => PermissionMode::AcceptEdits,
            ExternalPermissionMode::BypassPermissions => PermissionMode::BypassPermissions,
            ExternalPermissionMode::Default => PermissionMode::Default,
            ExternalPermissionMode::DontAsk => PermissionMode::DontAsk,
            ExternalPermissionMode::Plan => PermissionMode::Plan,
        }
    }
}

// ============================================================================
// Permission Behaviors
// ============================================================================

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PermissionBehavior {
    Allow,
    Deny,
    Ask,
}

// ============================================================================
// Permission Rules
// ============================================================================

/// Where a permission rule originated from.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum PermissionRuleSource {
    UserSettings,
    ProjectSettings,
    LocalSettings,
    FlagSettings,
    PolicySettings,
    CliArg,
    Command,
    Session,
}

/// The value of a permission rule - specifies which tool and optional content
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionRuleValue {
    pub tool_name: String,
    pub rule_content: Option<String>,
}

/// A permission rule with its source and behavior
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionRule {
    pub source: PermissionRuleSource,
    pub rule_behavior: PermissionBehavior,
    pub rule_value: PermissionRuleValue,
}

// ============================================================================
// Permission Updates
// ============================================================================

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum PermissionUpdateDestination {
    UserSettings,
    ProjectSettings,
    LocalSettings,
    Session,
    CliArg,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum PermissionUpdate {
    AddRules {
        destination: PermissionUpdateDestination,
        rules: Vec<PermissionRuleValue>,
        behavior: PermissionBehavior,
    },
    ReplaceRules {
        destination: PermissionUpdateDestination,
        rules: Vec<PermissionRuleValue>,
        behavior: PermissionBehavior,
    },
    RemoveRules {
        destination: PermissionUpdateDestination,
        rules: Vec<PermissionRuleValue>,
        behavior: PermissionBehavior,
    },
    SetMode {
        destination: PermissionUpdateDestination,
        mode: ExternalPermissionMode,
    },
    AddDirectories {
        destination: PermissionUpdateDestination,
        directories: Vec<String>,
    },
    RemoveDirectories {
        destination: PermissionUpdateDestination,
        directories: Vec<String>,
    },
}

/// Source of an additional working directory permission.
pub type WorkingDirectorySource = PermissionRuleSource;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AdditionalWorkingDirectory {
    pub path: String,
    pub source: WorkingDirectorySource,
}

// ============================================================================
// Permission Decisions & Results
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionCommandMetadata {
    pub name: String,
    pub description: Option<String>,
    #[serde(flatten)]
    pub extra: HashMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum PermissionMetadata {
    Command { command: PermissionCommandMetadata },
}

/// Metadata for a pending classifier check
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PendingClassifierCheck {
    pub command: String,
    pub cwd: String,
    pub descriptions: Vec<String>,
}

/// Result when permission is granted
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionAllowDecision {
    pub updated_input: Option<HashMap<String, Value>>,
    pub user_modified: Option<bool>,
    pub decision_reason: Option<PermissionDecisionReason>,
    pub tool_use_id: Option<String>,
    pub accept_feedback: Option<String>,
}

/// Result when user should be prompted
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionAskDecision {
    pub message: String,
    pub updated_input: Option<HashMap<String, Value>>,
    pub decision_reason: Option<PermissionDecisionReason>,
    pub suggestions: Option<Vec<PermissionUpdate>>,
    pub blocked_path: Option<String>,
    pub metadata: Option<PermissionMetadata>,
    pub is_bash_security_check_for_misparsing: Option<bool>,
    pub pending_classifier_check: Option<PendingClassifierCheck>,
}

/// Result when permission is denied
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionDenyDecision {
    pub message: String,
    pub decision_reason: PermissionDecisionReason,
    pub tool_use_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "behavior", rename_all = "lowercase")]
pub enum PermissionDecision {
    Allow(PermissionAllowDecision),
    Ask(PermissionAskDecision),
    Deny(PermissionDenyDecision),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "behavior", rename_all = "lowercase")]
pub enum PermissionResult {
    Allow(PermissionAllowDecision),
    Ask(PermissionAskDecision),
    Deny(PermissionDenyDecision),
    Passthrough {
        message: String,
        decision_reason: Option<Box<PermissionDecision>>,
        suggestions: Option<Vec<PermissionUpdate>>,
        blocked_path: Option<String>,
        pending_classifier_check: Option<PendingClassifierCheck>,
    },
}

/// Explanation of why a permission decision was made
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum PermissionDecisionReason {
    Rule { rule: PermissionRule },
    Mode { mode: PermissionMode },
    // Note: subcommandResults uses a Map in TS, using Vec<(String, PermissionResult)> in Rust
    SubcommandResults { reasons: Vec<(String, Box<PermissionResult>)> },
    PermissionPromptTool {
        permission_prompt_tool_name: String,
        tool_result: Value,
    },
    Hook {
        hook_name: String,
        hook_source: Option<String>,
        reason: Option<String>,
    },
    AsyncAgent { reason: String },
    SandboxOverride { reason: SandboxOverrideReason },
    Classifier {
        classifier: String,
        reason: String,
    },
    WorkingDir { reason: String },
    SafetyCheck {
        reason: String,
        classifier_approvable: bool,
    },
    Other { reason: String },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum SandboxOverrideReason {
    ExcludedCommand,
    DangerouslyDisableSandbox,
}

// ============================================================================
// Classifier Types
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ClassifierResult {
    pub matches: bool,
    pub matched_description: Option<String>,
    pub confidence: ClassifierConfidence,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ClassifierConfidence {
    High,
    Medium,
    Low,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ClassifierBehavior {
    Deny,
    Ask,
    Allow,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ClassifierUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_read_input_tokens: u64,
    pub cache_creation_input_tokens: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct YoloClassifierResult {
    pub thinking: Option<String>,
    pub should_block: bool,
    pub reason: String,
    pub unavailable: Option<bool>,
    pub transcript_too_long: Option<bool>,
    pub model: String,
    pub usage: Option<ClassifierUsage>,
    pub duration_ms: Option<u64>,
    pub prompt_lengths: Option<ClassifierPromptLengths>,
    pub error_dump_path: Option<String>,
    pub stage: Option<ClassifierStage>,
    pub stage1_usage: Option<ClassifierUsage>,
    pub stage1_duration_ms: Option<u64>,
    pub stage1_request_id: Option<String>,
    pub stage1_msg_id: Option<String>,
    pub stage2_usage: Option<ClassifierUsage>,
    pub stage2_duration_ms: Option<u64>,
    pub stage2_request_id: Option<String>,
    pub stage2_msg_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ClassifierPromptLengths {
    pub system_prompt: u64,
    pub tool_calls: u64,
    pub user_prompts: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ClassifierStage {
    Fast,
    Thinking,
}

// ============================================================================
// Permission Explainer Types
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RiskLevel {
    LOW,
    MEDIUM,
    HIGH,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionExplanation {
    pub risk_level: RiskLevel,
    pub explanation: String,
    pub reasoning: String,
    pub risk: String,
}

// ============================================================================
// Tool Permission Context
// ============================================================================

pub type ToolPermissionRulesBySource = HashMap<String, Vec<String>>;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolPermissionContext {
    pub mode: PermissionMode,
    pub additional_working_directories: HashMap<String, AdditionalWorkingDirectory>,
    pub always_allow_rules: ToolPermissionRulesBySource,
    pub always_deny_rules: ToolPermissionRulesBySource,
    pub always_ask_rules: ToolPermissionRulesBySource,
    pub is_bypass_permissions_mode_available: bool,
    pub stripped_dangerous_rules: Option<ToolPermissionRulesBySource>,
    pub should_avoid_permission_prompts: Option<bool>,
    pub await_automated_checks_before_dialog: Option<bool>,
    pub pre_plan_mode: Option<PermissionMode>,
}
