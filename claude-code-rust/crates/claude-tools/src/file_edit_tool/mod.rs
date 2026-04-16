// Original TS source: tools/FileEditTool/FileEditTool.ts
// File edit (str_replace) tool implementation

pub const FILE_EDIT_TOOL_NAME: &str = "Edit";

use std::collections::HashMap;
use std::path::Path;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use anyhow::{Context, Result, bail};
use async_trait::async_trait;
use crate::tool_base::{Tool, ToolInputSchema, ToolResult, ToolUseContext};

pub const FILE_UNEXPECTEDLY_MODIFIED_ERROR: &str =
    "File has been modified since it was last read. This is a safety check to prevent \
    overwriting edits. Please re-read the file and try again.";

/// Input for FileEditTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileEditInput {
    pub file_path: String,
    pub old_string: String,
    pub new_string: String,
}

/// The file edit tool (str_replace / multi-hunk replacement)
pub struct FileEditTool;

impl Default for FileEditTool {
    fn default() -> Self {
        Self
    }
}

/// Find occurrences of a substring in text, return positions and context.
pub fn find_occurrences(text: &str, pattern: &str) -> Vec<usize> {
    let mut positions = Vec::new();
    let mut start = 0;
    while let Some(pos) = text[start..].find(pattern) {
        positions.push(start + pos);
        start += pos + 1;
    }
    positions
}

/// Apply a str_replace edit to the given file content.
/// Returns the new content if exactly one match is found.
pub fn apply_str_replace(
    content: &str,
    old_string: &str,
    new_string: &str,
) -> Result<String> {
    let occurrences = find_occurrences(content, old_string);

    match occurrences.len() {
        0 => bail!(
            "No match found for:\n```\n{}\n```\n\nThe file may have been modified \
            or the search string is not an exact match.",
            old_string
        ),
        1 => Ok(content.replacen(old_string, new_string, 1)),
        n => bail!(
            "Found {} matches for the search string. Please use a more specific \
            string that uniquely identifies the section to edit.",
            n
        ),
    }
}

#[async_trait]
impl Tool for FileEditTool {
    fn name(&self) -> &str {
        FILE_EDIT_TOOL_NAME
    }

    fn description(&self) -> &str {
        "This is a tool for editing files. It replaces all occurrences of `old_string` with \
        `new_string` in the file at `file_path`. If `old_string` is empty, it inserts \
        `new_string` at the beginning of the file. This tool is best for targeted edits."
    }

    fn input_schema(&self) -> ToolInputSchema {
        let mut properties = HashMap::new();
        properties.insert("file_path".to_string(), serde_json::json!({
            "type": "string",
            "description": "The absolute path to the file to modify"
        }));
        properties.insert("old_string".to_string(), serde_json::json!({
            "type": "string",
            "description": "The text to search for in the file"
        }));
        properties.insert("new_string".to_string(), serde_json::json!({
            "type": "string",
            "description": "The text to replace old_string with"
        }));

        ToolInputSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec!["file_path".to_string(), "old_string".to_string(), "new_string".to_string()],
        }
    }

    async fn execute(&self, input: Value, context: &ToolUseContext) -> Result<ToolResult> {
        let edit_input: FileEditInput = serde_json::from_value(input)?;

        let path = Path::new(&edit_input.file_path);
        let resolved_path = if path.is_absolute() {
            path.to_path_buf()
        } else {
            Path::new(&context.cwd).join(path)
        };

        // Read existing content
        let content = tokio::fs::read_to_string(&resolved_path)
            .await
            .with_context(|| format!("Failed to read file: {}", resolved_path.display()))?;

        // If old_string is empty, prepend new_string
        let new_content = if edit_input.old_string.is_empty() {
            format!("{}{}", edit_input.new_string, content)
        } else {
            apply_str_replace(&content, &edit_input.old_string, &edit_input.new_string)?
        };

        // Write back
        tokio::fs::write(&resolved_path, &new_content)
            .await
            .with_context(|| format!("Failed to write file: {}", resolved_path.display()))?;

        Ok(ToolResult::text(format!(
            "Successfully edited {}",
            resolved_path.display()
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_occurrences() {
        let text = "hello world hello";
        let positions = find_occurrences(text, "hello");
        assert_eq!(positions.len(), 2);
    }

    #[test]
    fn test_apply_str_replace_single() {
        let content = "hello world";
        let result = apply_str_replace(content, "world", "rust").unwrap();
        assert_eq!(result, "hello rust");
    }

    #[test]
    fn test_apply_str_replace_not_found() {
        let content = "hello world";
        assert!(apply_str_replace(content, "xyz", "abc").is_err());
    }

    #[test]
    fn test_apply_str_replace_multiple() {
        let content = "hello hello";
        assert!(apply_str_replace(content, "hello", "world").is_err());
    }
}
