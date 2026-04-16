// Original TS source: tools/GrepTool/GrepTool.ts
// Grep/ripgrep tool for content search

pub const GREP_TOOL_NAME: &str = "Grep";

use std::collections::HashMap;
use std::path::Path;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use anyhow::Result;
use async_trait::async_trait;
use crate::tool_base::{Tool, ToolInputSchema, ToolResult, ToolUseContext};

const MAX_RESULTS: usize = 100;

/// Output mode for grep
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum OutputMode {
    Content,
    #[default]
    FilesWithMatches,
    Count,
}

/// Input for GrepTool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrepInput {
    pub pattern: String,
    pub path: Option<String>,
    pub glob: Option<String>,
    pub output_mode: Option<OutputMode>,
    #[serde(rename = "-B")]
    pub context_before: Option<u32>,
    #[serde(rename = "-A")]
    pub context_after: Option<u32>,
    #[serde(rename = "-C")]
    pub context: Option<u32>,
    pub head_limit: Option<usize>,
    #[serde(rename = "-n")]
    pub line_numbers: Option<bool>,
}

/// The grep search tool
pub struct GrepTool;

impl Default for GrepTool {
    fn default() -> Self {
        Self
    }
}

#[async_trait]
impl Tool for GrepTool {
    fn name(&self) -> &str {
        GREP_TOOL_NAME
    }

    fn description(&self) -> &str {
        "Fast content search tool that uses ripgrep to search for patterns in files. \
        Use this tool to search for text patterns in the codebase."
    }

    fn input_schema(&self) -> ToolInputSchema {
        let mut properties = HashMap::new();
        properties.insert("pattern".to_string(), serde_json::json!({
            "type": "string",
            "description": "The regular expression pattern to search for in file contents"
        }));
        properties.insert("path".to_string(), serde_json::json!({
            "type": "string",
            "description": "File or directory to search in. Defaults to current working directory."
        }));
        properties.insert("glob".to_string(), serde_json::json!({
            "type": "string",
            "description": "Glob pattern to filter files (e.g. \"*.js\", \"*.{ts,tsx}\")"
        }));
        properties.insert("output_mode".to_string(), serde_json::json!({
            "type": "string",
            "enum": ["content", "files_with_matches", "count"],
            "description": "Output mode: content, files_with_matches, or count"
        }));

        ToolInputSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec!["pattern".to_string()],
        }
    }

    async fn execute(&self, input: Value, context: &ToolUseContext) -> Result<ToolResult> {
        let grep_input: GrepInput = serde_json::from_value(input)?;

        let search_path = grep_input.path
            .as_deref()
            .unwrap_or(&context.cwd);

        // Try ripgrep first, fall back to built-in search
        match run_ripgrep(&grep_input, search_path).await {
            Ok(result) => Ok(ToolResult::text(result)),
            Err(_) => {
                // Fall back to built-in regex search
                run_builtin_grep(&grep_input, search_path).map(ToolResult::text)
            }
        }
    }
}

/// Run ripgrep if available
async fn run_ripgrep(input: &GrepInput, path: &str) -> Result<String> {
    let mut cmd = tokio::process::Command::new("rg");
    cmd.current_dir(path);

    // Output mode
    match input.output_mode.as_ref().unwrap_or(&OutputMode::FilesWithMatches) {
        OutputMode::Content => {
            if input.line_numbers.unwrap_or(false) {
                cmd.arg("-n");
            }
            if let Some(b) = input.context_before {
                cmd.args(["-B", &b.to_string()]);
            }
            if let Some(a) = input.context_after {
                cmd.args(["-A", &a.to_string()]);
            }
            if let Some(c) = input.context {
                cmd.args(["-C", &c.to_string()]);
            }
        }
        OutputMode::FilesWithMatches => {
            cmd.arg("-l");
        }
        OutputMode::Count => {
            cmd.arg("-c");
        }
    }

    if let Some(glob) = &input.glob {
        cmd.args(["-g", glob]);
    }

    cmd.arg(&input.pattern);
    cmd.arg(".");

    let output = cmd.output().await?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();

    if stdout.is_empty() && !output.status.success() {
        anyhow::bail!("ripgrep not available or search failed");
    }

    let limit = input.head_limit.unwrap_or(MAX_RESULTS);
    let lines: Vec<&str> = stdout.lines().take(limit).collect();

    Ok(lines.join("\n"))
}

/// Built-in grep using Rust regex
fn run_builtin_grep(input: &GrepInput, path: &str) -> Result<String> {
    use regex::Regex;

    let re = Regex::new(&input.pattern)?;
    let mut results = Vec::new();

    search_dir(path, &re, &mut results, &input.glob)?;

    let limit = input.head_limit.unwrap_or(MAX_RESULTS);
    let output: Vec<String> = results.into_iter().take(limit).collect();

    if output.is_empty() {
        Ok("No matches found.".to_string())
    } else {
        Ok(output.join("\n"))
    }
}

fn search_dir(
    dir: &str,
    re: &regex::Regex,
    results: &mut Vec<String>,
    glob: &Option<String>,
) -> Result<()> {
    let skip_dirs = [".git", "node_modules", "target", "dist", ".next"];

    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();

        if skip_dirs.contains(&name.as_str()) {
            continue;
        }

        if path.is_dir() {
            search_dir(&path.to_string_lossy(), re, results, glob)?;
        } else {
            // Check glob filter if present
            if let Some(glob_pattern) = glob {
                if !crate::glob_tool::matches_glob_pattern(glob_pattern, &name) {
                    continue;
                }
            }

            // Check for binary extension
            let ext = path.extension().and_then(|e| e.to_str()).map(|e| format!(".{}", e)).unwrap_or_default();
            if claude_constants::files::has_binary_extension(&ext) {
                continue;
            }

            if let Ok(content) = std::fs::read_to_string(&path) {
                if re.is_match(&content) {
                    results.push(path.to_string_lossy().to_string());
                }
            }
        }

        if results.len() >= MAX_RESULTS * 10 {
            break;
        }
    }

    Ok(())
}
