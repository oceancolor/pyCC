// Original TS source: utils/settings/types.ts, settings.ts
// Claude Code settings/configuration types

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Permissions section of settings
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionsSettings {
    pub allow: Option<Vec<String>>,
    pub deny: Option<Vec<String>>,
    pub ask: Option<Vec<String>>,
    pub default_mode: Option<String>,
    pub disable_bypass_permissions_mode: Option<String>,
    pub additional_directories: Option<Vec<String>>,
}

/// MCP server configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct McpServerSettings {
    pub command: Option<String>,
    pub args: Option<Vec<String>>,
    pub env: Option<HashMap<String, String>>,
    pub url: Option<String>,
    pub headers: Option<HashMap<String, String>>,
    pub transport: Option<String>,
    pub scope: Option<String>,
}

/// Model alias configuration (model: "opus" or "claude-opus-4-5-20251101")
pub type ModelConfig = String;

/// Hook configuration - reuse from types module
pub type HooksSettings = HashMap<String, Vec<Value>>; // hookEvent → [hookConfig]

/// Environment variable configuration
pub type EnvironmentVariables = HashMap<String, String>;

/// The main settings JSON schema
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SettingsJson {
    #[serde(rename = "$schema")]
    pub schema_url: Option<String>,

    // API configuration
    pub api_key: Option<String>,
    pub api_key_helper: Option<String>,

    // Model configuration
    pub model: Option<ModelConfig>,
    pub small_fast_model: Option<ModelConfig>,

    // Provider configuration
    pub bedrock_region: Option<String>,
    pub vertex_project_id: Option<String>,
    pub vertex_region: Option<String>,
    pub aws_profile: Option<String>,

    // Permissions
    pub permissions: Option<PermissionsSettings>,

    // Environment variables
    pub env: Option<EnvironmentVariables>,

    // MCP servers
    pub mcp_servers: Option<HashMap<String, McpServerSettings>>,

    // Hooks
    pub hooks: Option<HooksSettings>,

    // UI preferences
    pub theme: Option<String>,
    pub preferred_notify_sounds: Option<bool>,
    pub verbose: Option<bool>,
    pub clean_screenshots: Option<bool>,
    pub shift_enter_new_line: Option<bool>,
    pub show_thinking: Option<bool>,
    pub show_stats: Option<bool>,
    pub auto_compact: Option<String>, // "aggressive" | "normal" | "disabled"
    pub auto_compact_threshold: Option<u32>,
    pub max_thinking_tokens: Option<u32>,
    pub auto_summarize_mcp_tool_results: Option<bool>,
    pub effort: Option<String>, // "min" | "max" | "high" | "medium" | "low"
    pub notification_command: Option<String>,
    pub allowed_tools: Option<Vec<String>>,
    pub disabled_tools: Option<Vec<String>>,
    pub task_budgets: Option<HashMap<String, TaskBudgetConfig>>,
    pub allowed_mcp_tools: Option<Vec<String>>,
    pub disabled_mcp_tools: Option<Vec<String>>,
    pub output_format: Option<String>,
    pub include_co_authored_by: Option<bool>,
    pub web_search_config: Option<WebSearchConfig>,
    pub tool_search_config: Option<ToolSearchConfig>,
    pub context_1m: Option<String>, // "enable" | "disable"
    pub context_management: Option<ContextManagementSettings>,
    pub prompt_caching_scope: Option<String>,
    pub disable_prompt_caching: Option<bool>,
    pub disable_cache_warmup: Option<bool>,
    pub fast_edit_mode: Option<String>,
    pub append_system_prompt: Option<String>,
    pub bash_classifier: Option<String>,
    pub yolo_classifier: Option<String>,
    pub enable_notification: Option<bool>,

    // Proxy configuration
    pub proxy: Option<String>,
    pub bypass_proxy: Option<Vec<String>>,
    pub ssl_no_verify: Option<bool>,

    // Plugin settings
    pub enable_auto_updater: Option<bool>,

    /// Additional unknown settings fields
    #[serde(flatten)]
    pub extra: HashMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TaskBudgetConfig {
    pub max_tokens: Option<u64>,
    pub max_turns: Option<u64>,
    pub max_time_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WebSearchConfig {
    pub user: Option<String>,
    pub account: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolSearchConfig {
    pub user: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ContextManagementSettings {
    pub context_management_enabled: Option<bool>,
}

/// Source of a settings value
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum SettingSource {
    UserSettings,
    ProjectSettings,
    LocalSettings,
    FlagSettings,
    PolicySettings,
    MdmSettings,
    CliArg,
    Command,
    Session,
    Plugin,
}

impl SettingSource {
    pub fn is_user_editable(&self) -> bool {
        matches!(
            self,
            SettingSource::UserSettings
                | SettingSource::ProjectSettings
                | SettingSource::LocalSettings
        )
    }
}
