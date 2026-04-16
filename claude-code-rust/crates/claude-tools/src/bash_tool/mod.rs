// Original TS source: tools/BashTool/
// Bash tool implementation

pub mod permissions;

pub use self::permissions::bash_tool_has_permission;

pub const BASH_TOOL_NAME: &str = "Bash";

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use anyhow::Result;
use async_trait::async_trait;
use crate::tool_base::{Tool, ToolInputSchema, ToolResult, ToolUseContext};

/// Progress display threshold in milliseconds
pub const PROGRESS_THRESHOLD_MS: u64 = 2000;

/// In assistant mode, blocking bash auto-backgrounds after this many ms
pub const ASSISTANT_BLOCKING_BUDGET_MS: u64 = 15_000;

/// Bash commands that are considered search operations
pub const BASH_SEARCH_COMMANDS: &[&str] = &[
    "find", "grep", "rg", "ag", "ack", "locate", "which", "whereis",
];

/// Bash commands that are considered read operations
pub const BASH_READ_COMMANDS: &[&str] = &[
    "cat", "head", "tail", "less", "more",
    "wc", "stat", "file", "strings",
    "jq", "awk", "cut", "sort", "uniq", "tr",
];

/// Directory-listing commands
pub const BASH_LIST_COMMANDS: &[&str] = &["ls", "tree", "du"];

/// Commands that are semantic-neutral in any position
pub const BASH_SEMANTIC_NEUTRAL_COMMANDS: &[&str] = &[
    "echo", "printf", "true", "false", ":",
];

/// Commands that typically produce no stdout on success
pub const BASH_SILENT_COMMANDS: &[&str] = &[
    "mv", "cp", "rm", "mkdir", "rmdir", "chmod", "chown", "chgrp",
    "touch", "ln", "cd", "export", "unset", "wait",
];

/// Result of checking if a command is search or read
#[derive(Debug, Clone)]
pub struct CommandClassification {
    pub is_search: bool,
    pub is_read: bool,
    pub is_list: bool,
}

/// Checks if a bash command is a search or read operation.
pub fn is_search_or_read_bash_command(command: &str) -> CommandClassification {
    let first_word = command
        .split_whitespace()
        .next()
        .unwrap_or("")
        .split('/')
        .last()
        .unwrap_or("");

    let is_search = BASH_SEARCH_COMMANDS.contains(&first_word);
    let is_read = BASH_READ_COMMANDS.contains(&first_word);
    let is_list = BASH_LIST_COMMANDS.contains(&first_word);

    CommandClassification { is_search, is_read, is_list }
}

/// Input schema for BashTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BashInput {
    pub command: String,
    pub timeout: Option<u64>,
    pub description: Option<String>,
}

/// The Bash tool implementation
pub struct BashTool {
    pub default_timeout_ms: u64,
    pub max_timeout_ms: u64,
}

impl Default for BashTool {
    fn default() -> Self {
        Self {
            default_timeout_ms: 120_000,   // 2 minutes
            max_timeout_ms: 600_000,       // 10 minutes
        }
    }
}

#[async_trait]
impl Tool for BashTool {
    fn name(&self) -> &str {
        BASH_TOOL_NAME
    }

    fn description(&self) -> &str {
        "Executes a given bash command in a persistent shell session with optional timeout. \
        Useful for running code, managing files and directories, interacting with version control, \
        and any other shell commands."
    }

    fn input_schema(&self) -> ToolInputSchema {
        let mut properties = HashMap::new();
        properties.insert("command".to_string(), serde_json::json!({
            "type": "string",
            "description": "The bash command to run. Required unless the tool is being called with restart=true to restart the shell."
        }));
        properties.insert("timeout".to_string(), serde_json::json!({
            "type": "number",
            "description": "Optional timeout in milliseconds (max 600000)"
        }));
        properties.insert("description".to_string(), serde_json::json!({
            "type": "string",
            "description": "Clear, specific description of what this command does and why it needs to be executed"
        }));

        ToolInputSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec!["command".to_string()],
        }
    }

    async fn execute(&self, input: Value, context: &ToolUseContext) -> Result<ToolResult> {
        let bash_input: BashInput = serde_json::from_value(input)?;
        self.run_bash_command(bash_input, context).await
    }
}

impl BashTool {
    async fn run_bash_command(
        &self,
        input: BashInput,
        context: &ToolUseContext,
    ) -> Result<ToolResult> {
        let timeout_ms = input.timeout.unwrap_or(self.default_timeout_ms)
            .min(self.max_timeout_ms);

        let output = tokio::process::Command::new("bash")
            .arg("-c")
            .arg(&input.command)
            .current_dir(&context.cwd)
            .output()
            .await?;

        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        let exit_code = output.status.code().unwrap_or(-1);

        if exit_code == 0 {
            let result = if stderr.is_empty() {
                stdout
            } else {
                format!("{}\n<stderr>\n{}\n</stderr>", stdout, stderr)
            };
            Ok(ToolResult::text(result))
        } else {
            let error_msg = format!(
                "Exit code: {}\n<stdout>\n{}\n</stdout>\n<stderr>\n{}\n</stderr>",
                exit_code, stdout, stderr
            );
            Ok(ToolResult::error(error_msg))
        }
    }
}
