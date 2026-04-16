// 原始 TS: utils/messages.ts (5512 lines)
//! Message creation, normalization, and utility functions for the conversation loop.
//!
//! This is one of the largest and most complex files in the codebase.
//! Partial implementation — covers the most commonly used functions.
//! TODO: Complete full implementation.

use uuid::Uuid;
use serde::{Deserialize, Serialize};
use serde_json::Value;

// ── Message type aliases ──────────────────────────────────────────────────

pub type UUID = String;

// ── Content block types (mirrors Anthropic SDK) ──────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ContentBlock {
    Text {
        text: String,
    },
    ToolUse {
        id: String,
        name: String,
        input: Value,
    },
    ToolResult {
        tool_use_id: String,
        content: ToolResultContent,
        #[serde(skip_serializing_if = "Option::is_none")]
        is_error: Option<bool>,
    },
    Thinking {
        thinking: String,
    },
    RedactedThinking {
        data: String,
    },
    Image {
        source: ImageSource,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum ToolResultContent {
    Text(String),
    Blocks(Vec<ContentBlock>),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageSource {
    #[serde(rename = "type")]
    pub source_type: String, // "base64" | "url"
    #[serde(skip_serializing_if = "Option::is_none")]
    pub media_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
}

// ── API usage / cost tracking ─────────────────────────────────────────────

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ApiUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache_read_input_tokens: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache_creation_input_tokens: Option<u64>,
}

// ── Message types ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserMessage {
    #[serde(rename = "type")]
    pub kind: String, // "user"
    pub uuid: UUID,
    pub content: Vec<ContentBlock>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_use_result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_tool_assistant_uuid: Option<UUID>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssistantMessage {
    #[serde(rename = "type")]
    pub kind: String, // "assistant"
    pub uuid: UUID,
    pub message: ApiAssistantMessage,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub api_error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cost_usd: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub usage: Option<ApiUsage>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiAssistantMessage {
    pub role: String, // "assistant"
    pub content: Vec<ContentBlock>,
    pub model: String,
    pub stop_reason: Option<String>,
    pub usage: ApiUsage,
}

/// System/meta messages (non-API)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemMessage {
    #[serde(rename = "type")]
    pub kind: String, // "system"
    pub uuid: UUID,
    pub level: SystemMessageLevel,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SystemMessageLevel {
    Info,
    Warning,
    Error,
    Debug,
}

/// Compact boundary marker
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemCompactBoundaryMessage {
    #[serde(rename = "type")]
    pub kind: String, // "system_compact_boundary"
    pub uuid: UUID,
    pub summary_message_uuid: UUID,
}

/// Any message in a conversation
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Message {
    User(UserMessage),
    Assistant(AssistantMessage),
    System(SystemMessage),
    Attachment(AttachmentMessage),
    // Compact-related
    SystemCompactBoundary(SystemCompactBoundaryMessage),
    // Tombstone (deleted message placeholder)
    Tombstone(TombstoneMessage),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttachmentMessage {
    #[serde(rename = "type")]
    pub kind: String, // "attachment"
    pub uuid: UUID,
    pub content: String,
    pub attachment_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TombstoneMessage {
    #[serde(rename = "type")]
    pub kind: String, // "tombstone"
    pub uuid: UUID,
    pub original_uuid: UUID,
}

// ── Factory functions ────────────────────────────────────────────────────

/// Create a new UserMessage with a random UUID.
pub fn create_user_message(
    content: Vec<ContentBlock>,
    tool_use_result: Option<Value>,
    source_tool_assistant_uuid: Option<UUID>,
) -> UserMessage {
    UserMessage {
        kind: "user".to_string(),
        uuid: Uuid::new_v4().to_string(),
        content,
        tool_use_result,
        source_tool_assistant_uuid,
    }
}

/// Create a simple text user message.
pub fn create_text_user_message(text: impl Into<String>) -> UserMessage {
    create_user_message(
        vec![ContentBlock::Text { text: text.into() }],
        None,
        None,
    )
}

/// Create a system info message.
pub fn create_system_message(text: impl Into<String>) -> SystemMessage {
    SystemMessage {
        kind: "system".to_string(),
        uuid: Uuid::new_v4().to_string(),
        level: SystemMessageLevel::Info,
        message: text.into(),
    }
}

/// Create an assistant API error message.
pub fn create_assistant_api_error_message(
    error_type: impl Into<String>,
    content: Vec<ContentBlock>,
    model: impl Into<String>,
    usage: ApiUsage,
) -> AssistantMessage {
    AssistantMessage {
        kind: "assistant".to_string(),
        uuid: Uuid::new_v4().to_string(),
        message: ApiAssistantMessage {
            role: "assistant".to_string(),
            content,
            model: model.into(),
            stop_reason: None,
            usage,
        },
        api_error: Some(error_type.into()),
        cost_usd: None,
        duration_ms: None,
        usage: None,
    }
}

/// Create a compact boundary marker message.
pub fn create_compact_boundary_message(summary_message_uuid: UUID) -> SystemCompactBoundaryMessage {
    SystemCompactBoundaryMessage {
        kind: "system_compact_boundary".to_string(),
        uuid: Uuid::new_v4().to_string(),
        summary_message_uuid,
    }
}

/// Create a user interruption message for an aborted tool execution.
pub fn create_user_interruption_message(
    tool_use_id: impl Into<String>,
    error_message: impl Into<String>,
    source_tool_assistant_uuid: UUID,
) -> UserMessage {
    let tool_use_id = tool_use_id.into();
    let error_message = error_message.into();
    create_user_message(
        vec![ContentBlock::ToolResult {
            tool_use_id,
            content: ToolResultContent::Text(error_message.clone()),
            is_error: Some(true),
        }],
        Some(Value::String(error_message)),
        Some(source_tool_assistant_uuid),
    )
}

// ── Message query utilities ──────────────────────────────────────────────

/// Get the last AssistantMessage in a message list.
pub fn get_last_assistant_message(messages: &[Message]) -> Option<&AssistantMessage> {
    messages.iter().rev().find_map(|m| {
        if let Message::Assistant(a) = m {
            Some(a)
        } else {
            None
        }
    })
}

/// Get the text content of an AssistantMessage.
pub fn get_assistant_message_text(msg: &AssistantMessage) -> String {
    msg.message
        .content
        .iter()
        .filter_map(|block| {
            if let ContentBlock::Text { text } = block {
                Some(text.as_str())
            } else {
                None
            }
        })
        .collect::<Vec<_>>()
        .join("")
}

/// Check if a message is a compact boundary marker.
pub fn is_compact_boundary_message(msg: &Message) -> bool {
    matches!(msg, Message::SystemCompactBoundary(_))
}

/// Get all messages after the most recent compact boundary.
/// If no compact boundary found, return all messages.
pub fn get_messages_after_compact_boundary(messages: &[Message]) -> &[Message] {
    if let Some(pos) = messages
        .iter()
        .rposition(|m| is_compact_boundary_message(m))
    {
        &messages[pos..]
    } else {
        messages
    }
}

/// Normalize messages for API submission.
/// Removes system/meta messages and keeps only user/assistant messages.
/// Returns alternating user/assistant pairs as required by the API.
pub fn normalize_messages_for_api(messages: &[Message]) -> Vec<NormalizedMessage> {
    let mut result = Vec::new();
    let mut last_role: Option<&str> = None;

    for msg in messages {
        match msg {
            Message::User(u) => {
                // Merge consecutive user messages
                if last_role == Some("user") {
                    // TODO: merge into existing user message
                }
                result.push(NormalizedMessage::User {
                    role: "user".to_string(),
                    content: u.content.clone(),
                });
                last_role = Some("user");
            }
            Message::Assistant(a) => {
                result.push(NormalizedMessage::Assistant {
                    role: "assistant".to_string(),
                    content: a.message.content.clone(),
                });
                last_role = Some("assistant");
            }
            // Skip system, attachment, compact boundary, tombstone
            _ => {}
        }
    }
    result
}

/// Normalized message for Anthropic API submission.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "role", rename_all = "snake_case")]
pub enum NormalizedMessage {
    User {
        role: String,
        content: Vec<ContentBlock>,
    },
    Assistant {
        role: String,
        content: Vec<ContentBlock>,
    },
}

/// Count messages of a specific type.
pub fn count_messages_by_type(messages: &[Message], kind: &str) -> usize {
    messages
        .iter()
        .filter(|m| match m {
            Message::User(_) => kind == "user",
            Message::Assistant(_) => kind == "assistant",
            Message::System(_) => kind == "system",
            _ => false,
        })
        .count()
}

/// Strip signature blocks from text content.
/// Removes XML tags like <parameter name="signature">...