// Original TS source: types/logs.ts
// Log and transcript types

use std::collections::HashMap;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::message::Message;
use crate::ids::AgentId;

/// A serialized message with session metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SerializedMessage {
    #[serde(flatten)]
    pub message: Message,
    pub cwd: String,
    pub user_type: String,
    pub entrypoint: Option<String>,
    pub session_id: String,
    pub timestamp: String,
    pub version: String,
    pub git_branch: Option<String>,
    pub slug: Option<String>,
}

/// Log option for session listing
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LogOption {
    pub date: String,
    pub messages: Vec<SerializedMessage>,
    pub full_path: Option<String>,
    pub value: i64,
    pub created: DateTime<Utc>,
    pub modified: DateTime<Utc>,
    pub first_prompt: String,
    pub message_count: usize,
    pub file_size: Option<u64>,
    pub is_sidechain: bool,
    pub is_lite: Option<bool>,
    pub session_id: Option<String>,
    pub team_name: Option<String>,
    pub agent_name: Option<String>,
    pub agent_color: Option<String>,
    pub agent_setting: Option<String>,
    pub is_teammate: Option<bool>,
    pub leaf_uuid: Option<Uuid>,
    pub summary: Option<String>,
    pub custom_title: Option<String>,
    pub tag: Option<String>,
}

/// Summary message
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SummaryMessage {
    #[serde(rename = "type")]
    pub msg_type: String, // "summary"
    pub leaf_uuid: Uuid,
    pub summary: String,
}

/// Custom title message
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CustomTitleMessage {
    #[serde(rename = "type")]
    pub msg_type: String, // "custom-title"
    pub session_id: Uuid,
    pub custom_title: String,
}

/// AI-generated session title
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AiTitleMessage {
    #[serde(rename = "type")]
    pub msg_type: String, // "ai-title"
    pub session_id: Uuid,
    pub ai_title: String,
}

/// Tag message for session tagging
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TagMessage {
    #[serde(rename = "type")]
    pub msg_type: String, // "tag"
    pub session_id: Uuid,
    pub tag: String,
}

/// Agent name message
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentNameMessage {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub session_id: Uuid,
    pub agent_name: String,
}

/// Agent color message
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentColorMessage {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub session_id: Uuid,
    pub agent_color: String,
}

/// PR link message
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PRLinkMessage {
    #[serde(rename = "type")]
    pub msg_type: String, // "pr-link"
    pub session_id: Uuid,
    pub pr_number: u64,
    pub pr_url: String,
    pub pr_repository: String,
    pub timestamp: String,
}

/// Session mode entry
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ModeEntry {
    #[serde(rename = "type")]
    pub msg_type: String, // "mode"
    pub session_id: Uuid,
    pub mode: SessionMode,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SessionMode {
    Coordinator,
    Normal,
}

/// Persisted worktree session state
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PersistedWorktreeSession {
    pub original_cwd: String,
    pub worktree_path: String,
    pub worktree_name: String,
    pub worktree_branch: Option<String>,
    pub original_branch: Option<String>,
    pub original_head_commit: Option<String>,
    pub session_id: String,
    pub tmux_session_name: Option<String>,
    pub hook_based: Option<bool>,
}

/// Worktree state entry
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WorktreeStateEntry {
    #[serde(rename = "type")]
    pub msg_type: String, // "worktree-state"
    pub session_id: Uuid,
    pub worktree_session: Option<PersistedWorktreeSession>,
}

/// Per-file attribution state
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileAttributionState {
    pub content_hash: String,
    pub claude_contribution: u64,
    pub mtime: u64,
}

/// Attribution snapshot message
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AttributionSnapshotMessage {
    #[serde(rename = "type")]
    pub msg_type: String, // "attribution-snapshot"
    pub message_id: Uuid,
    pub surface: String,
    pub file_states: HashMap<String, FileAttributionState>,
    pub prompt_count: Option<u64>,
    pub prompt_count_at_last_commit: Option<u64>,
    pub permission_prompt_count: Option<u64>,
    pub permission_prompt_count_at_last_commit: Option<u64>,
    pub escape_count: Option<u64>,
    pub escape_count_at_last_commit: Option<u64>,
}

/// Transcript message (extends SerializedMessage)
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TranscriptMessage {
    #[serde(flatten)]
    pub serialized: SerializedMessage,
    pub parent_uuid: Option<Uuid>,
    pub logical_parent_uuid: Option<Uuid>,
    pub is_sidechain: bool,
    pub git_branch: Option<String>,
    pub agent_id: Option<String>,
    pub team_name: Option<String>,
    pub agent_name: Option<String>,
    pub agent_color: Option<String>,
    pub prompt_id: Option<String>,
}

/// Content replacement entry
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ContentReplacementEntry {
    #[serde(rename = "type")]
    pub msg_type: String, // "content-replacement"
    pub session_id: Uuid,
    pub agent_id: Option<AgentId>,
    pub replacements: Vec<serde_json::Value>, // ContentReplacementRecord
}

/// Context collapse commit entry
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ContextCollapseCommitEntry {
    #[serde(rename = "type")]
    pub msg_type: String, // "marble-origami-commit"
    pub session_id: Uuid,
    pub collapse_id: String,
    pub summary_uuid: String,
    pub summary_content: String,
    pub summary: String,
    pub first_archived_uuid: String,
    pub last_archived_uuid: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StagedCollapseEntry {
    pub start_uuid: String,
    pub end_uuid: String,
    pub summary: String,
    pub risk: f64,
    pub staged_at: u64,
}

/// Context collapse snapshot entry
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ContextCollapseSnapshotEntry {
    #[serde(rename = "type")]
    pub msg_type: String, // "marble-origami-snapshot"
    pub session_id: Uuid,
    pub staged: Vec<StagedCollapseEntry>,
    pub armed: bool,
    pub last_spawn_tokens: u64,
}

/// Sort logs by modified date (newest first)
pub fn sort_logs(mut logs: Vec<LogOption>) -> Vec<LogOption> {
    logs.sort_by(|a, b| {
        let modified_diff = b.modified.cmp(&a.modified);
        if modified_diff != std::cmp::Ordering::Equal {
            return modified_diff;
        }
        b.created.cmp(&a.created)
    });
    logs
}
