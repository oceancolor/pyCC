// Original TS source: tools/FileWriteTool/FileWriteTool.ts
// File write tool implementation

pub const FILE_WRITE_TOOL_NAME: &str = "Write";

use std::collections::HashMap;
use std::path::Path;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use anyhow::{Context, Result};
use async_trait::async_trait;
use crate::tool_base::{Tool, ToolInputSchema, ToolResult, ToolUseContext};

/// Input for FileWriteTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileWriteInput {
    pub file_path: String,
    pub content: String,
}

/// Output from FileWriteTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileWriteOutput {
    #[serde(rename = "type")]
    pub write_type: FileWriteType,
    pub file_path: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FileWriteType {
    Create,
    Update,
}

/// The file write tool
pub struct FileWriteTool;

impl Default for FileWriteTool {
    fn default() -> Self {
        Self
    }
}

#[async_trait]
impl Tool for FileWriteTool {
    fn name(&self) -> &str {
        FILE_WRITE_TOOL_NAME
    }

    fn description(&self) -> &str {
        "Write a file to the local filesystem. Overwrites the existing file if there is one. \
        Creates the necessary directories if they don't exist."
    }

    fn input_schema(&self) -> ToolInputSchema {
        let mut properties = HashMap::new();
        properties.insert("file_path".to_string(), serde_json::json!({
            "type": "string",
            "description": "The absolute path to the file to write (must be absolute, not relative)"
        }));
        properties.insert("content".to_string(), serde_json::json!({
            "type": "string",
            "description": "The content to write to the file"
        }));

        ToolInputSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec!["file_path".to_string(), "content".to_string()],
        }
    }

    async fn execute(&self, input: Value, context: &ToolUseContext) -> Result<ToolResult> {
        let write_input: FileWriteInput = serde_json::from_value(input)?;

        let path = Path::new(&write_input.file_path);
        let resolved_path = if path.is_absolute() {
            path.to_path_buf()
        } else {
            Path::new(&context.cwd).join(path)
        };

        // Create parent directories if needed
        if let Some(parent) = resolved_path.parent() {
            tokio::fs::create_dir_all(parent)
                .await
                .with_context(|| format!("Failed to create directories for: {}", resolved_path.display()))?;
        }

        let write_type = if resolved_path.exists() {
            FileWriteType::Update
        } else {
            FileWriteType::Create
        };

        // Write the file
        tokio::fs::write(&resolved_path, &write_input.content)
            .await
            .with_context(|| format!("Failed to write file: {}", resolved_path.display()))?;

        let msg = match write_type {
            FileWriteType::Create => format!("Created file {}", resolved_path.display()),
            FileWriteType::Update => format!("Updated file {}", resolved_path.display()),
        };

        Ok(ToolResult::text(msg))
    }
}
