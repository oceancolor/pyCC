// Original TS source: tools/FileReadTool/FileReadTool.ts
// File read tool implementation

pub const FILE_READ_TOOL_NAME: &str = "Read";

use std::collections::HashMap;
use std::path::Path;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use anyhow::{Context, Result};
use async_trait::async_trait;
use crate::tool_base::{Tool, ToolInputSchema, ToolResult, ToolUseContext};

/// Input schema for FileReadTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileReadInput {
    pub file_path: String,
    pub offset: Option<u64>,
    pub limit: Option<u64>,
}

/// File read tool
pub struct FileReadTool;

impl Default for FileReadTool {
    fn default() -> Self {
        Self
    }
}

/// Default limits for file reading
pub struct FileReadLimits {
    pub max_lines: u64,
    pub max_file_size: u64,
}

impl Default for FileReadLimits {
    fn default() -> Self {
        Self {
            max_lines: 2000,
            max_file_size: 100 * 1024, // 100 KB
        }
    }
}

/// Add line numbers to file content
pub fn add_line_numbers(content: &str, start_line: u64) -> String {
    content
        .lines()
        .enumerate()
        .map(|(i, line)| format!("{:5}\t{}", start_line + i as u64 + 1, line))
        .collect::<Vec<_>>()
        .join("\n")
}

/// Read a file in a specific line range
pub async fn read_file_in_range(
    path: &Path,
    offset: Option<u64>,
    limit: Option<u64>,
) -> Result<(String, bool)> {
    let content = tokio::fs::read_to_string(path)
        .await
        .with_context(|| format!("Failed to read file: {}", path.display()))?;

    let lines: Vec<&str> = content.lines().collect();
    let total_lines = lines.len() as u64;

    let start = offset.unwrap_or(0);
    let max_lines = limit.unwrap_or(2000);
    let end = (start + max_lines).min(total_lines);

    let truncated = end < total_lines;
    let selected_lines: Vec<&str> = lines[start as usize..end as usize].to_vec();
    let result_content = selected_lines.join("\n");
    let numbered = add_line_numbers(&result_content, start);

    Ok((numbered, truncated))
}

#[async_trait]
impl Tool for FileReadTool {
    fn name(&self) -> &str {
        FILE_READ_TOOL_NAME
    }

    fn description(&self) -> &str {
        "Reads a file from the local filesystem. You can optionally specify a line offset and limit to read a portion of the file. \
        Without offset/limit, reads up to 2000 lines. Longer files can be read by using the offset parameter."
    }

    fn input_schema(&self) -> ToolInputSchema {
        let mut properties = HashMap::new();
        properties.insert("file_path".to_string(), serde_json::json!({
            "type": "string",
            "description": "The absolute path to the file to read"
        }));
        properties.insert("offset".to_string(), serde_json::json!({
            "type": "number",
            "description": "The line number to start reading from (0-indexed)"
        }));
        properties.insert("limit".to_string(), serde_json::json!({
            "type": "number",
            "description": "The number of lines to read"
        }));

        ToolInputSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec!["file_path".to_string()],
        }
    }

    async fn execute(&self, input: Value, context: &ToolUseContext) -> Result<ToolResult> {
        let file_input: FileReadInput = serde_json::from_value(input)?;

        let path = Path::new(&file_input.file_path);

        // Check if path is absolute or make it relative to cwd
        let resolved_path = if path.is_absolute() {
            path.to_path_buf()
        } else {
            Path::new(&context.cwd).join(path)
        };

        // Check for binary extension
        let ext = resolved_path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| format!(".{}", e))
            .unwrap_or_default();

        if claude_constants::files::has_binary_extension(&ext) {
            return Ok(ToolResult::error(
                "This is a binary file and cannot be read as text."
            ));
        }

        match read_file_in_range(&resolved_path, file_input.offset, file_input.limit).await {
            Ok((content, truncated)) => {
                let result = if truncated {
                    format!(
                        "{}\n\n(File truncated. Use offset parameter to read more.)",
                        content
                    )
                } else {
                    content
                };
                Ok(ToolResult::text(result))
            }
            Err(e) => Ok(ToolResult::error(e.to_string())),
        }
    }
}
