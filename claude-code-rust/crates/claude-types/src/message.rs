// Original TS source: types/message.ts (inferred from usage)
// Core message types for Claude Code

use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

/// Origin of a message - where it came from
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum MessageOrigin {
    Human,
    Bridge,
    Mcp,
    Cron,
    Teammate,
    Resource,
    Proactive,
}

/// Content block types in messages
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ContentBlock {
    Text {
        text: String,
    },
    Image {
        source: ImageSource,
    },
    ToolUse {
        id: String,
        name: String,
        input: Value,
    },
    ToolResult {
        tool_use_id: String,
        content: Option<Vec<ToolResultContent>>,
        is_error: Option<bool>,
    },
    Document {
        source: DocumentSource,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ImageSource {
    Base64 {
        media_type: String,
        data: String,
    },
    Url {
        url: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum DocumentSource {
    Base64 {
        media_type: String,
        data: String,
    },
    Text {
        text: String,
    },
    Url {
        url: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ToolResultContent {
    Text { text: String },
    Image { source: ImageSource },
}

/// A user message
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UserMessage {
    pub id: Option<Uuid>,
    pub role: String,  // "user"
    pub content: Vec<ContentBlock>,
    pub is_meta: Option<bool>,
    pub origin: Option<MessageOrigin>,
}

/// An assistant message
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AssistantMessage {
    pub id: Option<Uuid>,
    pub role: String,  // "assistant"
    pub content: Vec<ContentBlock>,
    pub model: Option<String>,
    pub stop_reason: Option<String>,
    pub usage: Option<MessageUsage>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MessageUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_read_input_tokens: Option<u64>,
    pub cache_creation_input_tokens: Option<u64>,
}

/// Discriminated union of all message types
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "role", rename_all = "lowercase")]
pub enum Message {
    User(UserMessage),
    Assistant(AssistantMessage),
}

impl Message {
    pub fn is_user(&self) -> bool {
        matches!(self, Message::User(_))
    }

    pub fn is_assistant(&self) -> bool {
        matches!(self, Message::Assistant(_))
    }
}
