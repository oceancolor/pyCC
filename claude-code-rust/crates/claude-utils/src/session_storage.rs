// Original TS source: utils/sessionStorage.ts
// Session persistence and transcript management
// NOTE: Full implementation is complex (JSONL files, concurrent writes, etc.)
//       This stub covers the essential data structures and API.

use std::path::{Path, PathBuf};
use anyhow::Result;
use serde_json::Value;
use uuid::Uuid;

use crate::env_utils::get_claude_config_home_dir;

/// Get the transcript path for a session.
pub fn get_transcript_path(session_id: &str, cwd: &Path) -> PathBuf {
    // Convert cwd to a slug: replace '/' with '-', remove leading '-'
    let project_slug = cwd.to_string_lossy()
        .replace(std::path::MAIN_SEPARATOR, "-")
        .trim_start_matches('-')
        .to_string();

    get_claude_config_home_dir()
        .join("projects")
        .join(&project_slug)
        .join(format!("{}.jsonl", session_id))
}

/// Parse a JSONL file into a list of JSON values.
pub fn parse_jsonl(content: &str) -> Vec<Value> {
    content
        .lines()
        .filter(|l| !l.trim().is_empty())
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect()
}

/// Write a single JSONL record to a file (append mode).
pub async fn append_jsonl_record(path: &Path, value: &Value) -> Result<()> {
    let line = serde_json::to_string(value)?;
    let content = format!("{}\n", line);
    
    // Create parent directory if needed
    if let Some(parent) = path.parent() {
        tokio::fs::create_dir_all(parent).await?;
    }
    
    // Append to file
    let mut file = tokio::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .await?;
    
    tokio::io::AsyncWriteExt::write_all(&mut file, content.as_bytes()).await?;
    Ok(())
}

/// Read all records from a JSONL transcript file.
pub async fn read_transcript(path: &Path) -> Result<Vec<Value>> {
    if !path.exists() {
        return Ok(vec![]);
    }
    let content = tokio::fs::read_to_string(path).await?;
    Ok(parse_jsonl(&content))
}

/// Get all session paths for a project directory.
pub async fn get_session_paths_for_dir(project_dir: &Path) -> Result<Vec<PathBuf>> {
    if !project_dir.exists() {
        return Ok(vec![]);
    }
    
    let mut paths = Vec::new();
    let mut entries = tokio::fs::read_dir(project_dir).await?;
    
    while let Some(entry) = entries.next_entry().await? {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) == Some("jsonl") {
            paths.push(path);
        }
    }
    
    paths.sort();
    Ok(paths)
}

/// Generate a summary entry for a session.
pub fn make_summary_entry(
    session_id: &Uuid,
    summary: &str,
    leaf_uuid: &Uuid,
) -> Value {
    serde_json::json!({
        "type": "summary",
        "sessionId": session_id.to_string(),
        "summary": summary,
        "leafUuid": leaf_uuid.to_string(),
    })
}
