// Original TS source: Tool.ts, tool_base
// Base trait for all tools

use std::collections::HashMap;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use anyhow::Result;

/// Tool use context passed to each tool invocation
#[derive(Debug, Clone)]
pub struct ToolUseContext {
    pub cwd: String,
    pub session_id: String,
    pub agent_id: Option<String>,
    pub permission_mode: String,
    pub is_non_interactive: bool,
}

/// Result of a tool invocation
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ToolResult {
    Text { text: String },
    Error { text: String },
}

impl ToolResult {
    pub fn text(text: impl Into<String>) -> Self {
        ToolResult::Text { text: text.into() }
    }

    pub fn error(text: impl Into<String>) -> Self {
        ToolResult::Error { text: text.into() }
    }

    pub fn is_error(&self) -> bool {
        matches!(self, ToolResult::Error { .. })
    }
}

/// Tool input schema (JSON Schema)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolInputSchema {
    #[serde(rename = "type")]
    pub schema_type: String,
    pub properties: HashMap<String, Value>,
    pub required: Vec<String>,
}

/// Tool definition metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    pub input_schema: ToolInputSchema,
}

/// Core tool trait
#[async_trait]
pub trait Tool: Send + Sync {
    /// Return the tool's name
    fn name(&self) -> &str;

    /// Return the tool's description
    fn description(&self) -> &str;

    /// Return the tool's JSON input schema
    fn input_schema(&self) -> ToolInputSchema;

    /// Execute the tool with the given input
    async fn execute(
        &self,
        input: Value,
        context: &ToolUseContext,
    ) -> Result<ToolResult>;

    /// Validate input before execution
    fn validate_input(&self, input: &Value) -> Result<()> {
        // Default: no extra validation
        Ok(())
    }
}

/// Validation result
#[derive(Debug, Clone)]
pub struct ValidationResult {
    pub valid: bool,
    pub error: Option<String>,
}

impl ValidationResult {
    pub fn ok() -> Self {
        Self { valid: true, error: None }
    }

    pub fn err(msg: impl Into<String>) -> Self {
        Self { valid: false, error: Some(msg.into()) }
    }
}
