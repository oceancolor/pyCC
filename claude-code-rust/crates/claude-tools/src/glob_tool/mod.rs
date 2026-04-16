// Original TS source: tools/GlobTool/GlobTool.ts
// Glob file search tool

pub const GLOB_TOOL_NAME: &str = "Glob";

use std::collections::HashMap;
use std::path::Path;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use anyhow::Result;
use async_trait::async_trait;
use crate::tool_base::{Tool, ToolInputSchema, ToolResult, ToolUseContext};

const MAX_RESULTS: usize = 100;

/// Input for GlobTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlobInput {
    pub pattern: String,
    pub path: Option<String>,
}

/// Output from GlobTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlobOutput {
    pub duration_ms: u64,
    pub num_files: usize,
    pub filenames: Vec<String>,
    pub truncated: bool,
}

/// The glob search tool
pub struct GlobTool;

impl Default for GlobTool {
    fn default() -> Self {
        Self
    }
}

/// Simple glob pattern matching
/// Supports * (any chars), ? (single char), ** (any path component)
pub fn matches_glob_pattern(pattern: &str, path: &str) -> bool {
    // For complex glob matching, we'd use the `glob` crate
    // Simple implementation: convert glob to regex and match
    let mut regex_parts = String::from("^");
    let chars: Vec<char> = pattern.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        match chars[i] {
            '*' => {
                if i + 1 < chars.len() && chars[i + 1] == '*' {
                    regex_parts.push_str(".*");
                    i += 2;
                    if i < chars.len() && chars[i] == '/' {
                        i += 1;
                    }
                    continue;
                } else {
                    regex_parts.push_str("[^/]*");
                }
            }
            '?' => regex_parts.push_str("[^/]"),
            '.' | '+' | '^' | '$' | '{' | '}' | '[' | ']' | '(' | ')' | '|' => {
                regex_parts.push('\\');
                regex_parts.push(chars[i]);
            }
            c => regex_parts.push(c),
        }
        i += 1;
    }
    regex_parts.push('$');

    regex::Regex::new(&regex_parts)
        .map(|r| r.is_match(path))
        .unwrap_or(false)
}

#[async_trait]
impl Tool for GlobTool {
    fn name(&self) -> &str {
        GLOB_TOOL_NAME
    }

    fn description(&self) -> &str {
        "Fast file pattern matching tool that works with any codebase size. \
        Searches for files matching a glob pattern, outputting file paths sorted by modification time. \
        Use this tool when you need to find files by name pattern."
    }

    fn input_schema(&self) -> ToolInputSchema {
        let mut properties = HashMap::new();
        properties.insert("pattern".to_string(), serde_json::json!({
            "type": "string",
            "description": "The glob pattern to match files against"
        }));
        properties.insert("path".to_string(), serde_json::json!({
            "type": "string",
            "description": "The directory to search in. Defaults to current working directory."
        }));

        ToolInputSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec!["pattern".to_string()],
        }
    }

    async fn execute(&self, input: Value, context: &ToolUseContext) -> Result<ToolResult> {
        let glob_input: GlobInput = serde_json::from_value(input)?;

        let search_dir = glob_input.path
            .as_deref()
            .unwrap_or(&context.cwd);

        let start_time = std::time::Instant::now();
        let mut matches = Vec::new();

        // Walk the directory tree
        if let Err(e) = walk_dir(Path::new(search_dir), &glob_input.pattern, &mut matches) {
            return Ok(ToolResult::error(e.to_string()));
        }

        // Sort by path
        matches.sort();

        let truncated = matches.len() > MAX_RESULTS;
        if truncated {
            matches.truncate(MAX_RESULTS);
        }

        let duration_ms = start_time.elapsed().as_millis() as u64;

        if matches.is_empty() {
            return Ok(ToolResult::text("No files found."));
        }

        let output = GlobOutput {
            duration_ms,
            num_files: matches.len(),
            filenames: matches.clone(),
            truncated,
        };

        let mut result = matches.join("\n");
        if truncated {
            result.push_str("\n\n(Results truncated to 100 files.)");
        }

        Ok(ToolResult::text(result))
    }
}

fn walk_dir(dir: &Path, pattern: &str, matches: &mut Vec<String>) -> Result<()> {
    if !dir.is_dir() {
        return Ok(());
    }

    // Check for gitignore-like patterns to skip
    let skip_dirs = [".git", "node_modules", ".next", "target", "dist"];

    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        let file_name = entry.file_name();
        let name = file_name.to_string_lossy();

        if skip_dirs.contains(&name.as_ref()) {
            continue;
        }

        if path.is_dir() {
            walk_dir(&path, pattern, matches)?;
        } else {
            let path_str = path.to_string_lossy().to_string();
            // Match against just the filename or the full path pattern
            let relative = path.file_name().unwrap_or_default().to_string_lossy().to_string();
            if matches_glob_pattern(pattern, &relative) || matches_glob_pattern(pattern, &path_str) {
                matches.push(path_str);
            }
        }

        if matches.len() >= MAX_RESULTS * 10 {
            break; // Safety limit
        }
    }

    Ok(())
}
