// Original TS source: query.ts
// Core agentic query loop - executes messages, handles tool_use, loops until stop

use std::collections::HashMap;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tracing::{debug, warn};

use crate::AnthropicClient;
use claude_tools::tool_base::{Tool, ToolDefinition, ToolResult, ToolUseContext};
use claude_types::message::{ContentBlock, Message, MessageUsage};

// ─── Public Types ────────────────────────────────────────────────────────────

/// Options for a single agentic query run
#[derive(Debug, Clone)]
pub struct QueryOptions {
    /// The model to use (e.g. "claude-opus-4-5")
    pub model: String,

    /// Optional system prompt
    pub system_prompt: Option<String>,

    /// Conversation messages (user/assistant turns)
    pub messages: Vec<Message>,

    /// Max agentic loop iterations (prevents infinite tool loops)
    pub max_iterations: usize,

    /// Max output tokens per API call
    pub max_tokens: u32,

    /// Tool execution context (cwd, session_id, etc.)
    pub tool_context: ToolUseContext,

    /// Optional stop sequences
    pub stop_sequences: Vec<String>,

    /// Whether to stream (currently unused - kept for future streaming support)
    pub stream: bool,
}

impl Default for QueryOptions {
    fn default() -> Self {
        Self {
            model: "claude-opus-4-5".to_string(),
            system_prompt: None,
            messages: Vec::new(),
            max_iterations: 10,
            max_tokens: 8096,
            tool_context: ToolUseContext {
                cwd: std::env::current_dir()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string(),
                session_id: uuid::Uuid::new_v4().to_string(),
                agent_id: None,
                permission_mode: "default".to_string(),
                is_non_interactive: false,
            },
            stop_sequences: Vec::new(),
            stream: false,
        }
    }
}

/// Token usage statistics
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct UsageInfo {
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub cache_creation_input_tokens: u32,
    pub cache_read_input_tokens: u32,
}

impl UsageInfo {
    /// Accumulate usage from an API response usage object
    pub fn accumulate(&mut self, usage: &Value) {
        self.input_tokens += usage["input_tokens"].as_u64().unwrap_or(0) as u32;
        self.output_tokens += usage["output_tokens"].as_u64().unwrap_or(0) as u32;
        self.cache_creation_input_tokens +=
            usage["cache_creation_input_tokens"].as_u64().unwrap_or(0) as u32;
        self.cache_read_input_tokens +=
            usage["cache_read_input_tokens"].as_u64().unwrap_or(0) as u32;
    }
}

/// Result of a complete agentic query run
#[derive(Debug, Clone)]
pub struct QueryResult {
    /// All messages (original + new assistant/user turns added during the run)
    pub messages: Vec<Message>,

    /// The final stop reason ("end_turn", "stop_sequence", "max_tokens", etc.)
    pub stop_reason: String,

    /// Cumulative token usage across all API calls in the loop
    pub usage: UsageInfo,

    /// How many iterations the loop actually ran
    pub iterations: usize,
}

// ─── Internal Helpers ────────────────────────────────────────────────────────

/// Build the `tools` array for the API request from the tool slice
fn build_tools_json(tools: &[Box<dyn Tool>]) -> Vec<Value> {
    tools
        .iter()
        .map(|t| {
            let def: ToolDefinition = ToolDefinition {
                name: t.name().to_string(),
                description: t.description().to_string(),
                input_schema: t.input_schema(),
            };
            json!({
                "name": def.name,
                "description": def.description,
                "input_schema": {
                    "type": def.input_schema.schema_type,
                    "properties": def.input_schema.properties,
                    "required": def.input_schema.required,
                }
            })
        })
        .collect()
}

/// Normalise our `Message` vec into the API-compatible array format.
/// Each message becomes `{ role, content: [...] }`.
fn messages_to_api(messages: &[Message]) -> Vec<Value> {
    messages
        .iter()
        .filter_map(|msg| match msg {
            Message::User(u) => {
                let content = content_blocks_to_api(&u.content);
                Some(json!({ "role": "user", "content": content }))
            }
            Message::Assistant(a) => {
                let content = content_blocks_to_api(&a.content);
                Some(json!({ "role": "assistant", "content": content }))
            }
            // Tombstone / attachment / summary messages are internal – skip them
            _ => None,
        })
        .collect()
}

/// Serialise a slice of ContentBlock into API JSON
fn content_blocks_to_api(blocks: &[ContentBlock]) -> Vec<Value> {
    blocks
        .iter()
        .map(|b| match b {
            ContentBlock::Text { text } => json!({ "type": "text", "text": text }),
            ContentBlock::Image { source } => json!({ "type": "image", "source": source }),
            ContentBlock::ToolUse { id, name, input } => json!({
                "type": "tool_use",
                "id": id,
                "name": name,
                "input": input,
            }),
            ContentBlock::ToolResult { tool_use_id, content, is_error } => {
                let mut v = json!({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                });
                if let Some(c) = content {
                    v["content"] = json!(c);
                }
                if let Some(e) = is_error {
                    v["is_error"] = json!(e);
                }
                v
            }
            ContentBlock::Document { source } => json!({ "type": "document", "source": source }),
        })
        .collect()
}

/// Convert an API response `content` array back into our `ContentBlock` vec
fn api_content_to_blocks(content: &[Value]) -> Vec<ContentBlock> {
    content
        .iter()
        .filter_map(|c| {
            match c["type"].as_str()? {
                "text" => Some(ContentBlock::Text {
                    text: c["text"].as_str().unwrap_or("").to_string(),
                }),
                "tool_use" => Some(ContentBlock::ToolUse {
                    id: c["id"].as_str().unwrap_or("").to_string(),
                    name: c["name"].as_str().unwrap_or("").to_string(),
                    input: c["input"].clone(),
                }),
                _ => None,
            }
        })
        .collect()
}

/// Build the full API request body
fn build_request(options: &QueryOptions, messages: &[Message], tools: &[Box<dyn Tool>]) -> Value {
    let mut req = json!({
        "model": options.model,
        "max_tokens": options.max_tokens,
        "messages": messages_to_api(messages),
    });

    if let Some(sys) = &options.system_prompt {
        req["system"] = json!(sys);
    }

    if !tools.is_empty() {
        req["tools"] = json!(build_tools_json(tools));
    }

    if !options.stop_sequences.is_empty() {
        req["stop_sequences"] = json!(options.stop_sequences);
    }

    req
}

/// Execute all `tool_use` blocks in an assistant response.
/// Returns a new user message containing the corresponding `tool_result` blocks.
async fn execute_tool_uses(
    tool_use_blocks: &[Value],
    tools: &[Box<dyn Tool>],
    ctx: &ToolUseContext,
) -> Vec<ContentBlock> {
    let mut results: Vec<ContentBlock> = Vec::new();

    for block in tool_use_blocks {
        let id = block["id"].as_str().unwrap_or("").to_string();
        let name = block["name"].as_str().unwrap_or("");
        let input = block["input"].clone();

        debug!("Executing tool: {} (id={})", name, id);

        // Find matching tool
        let tool_result = match tools.iter().find(|t| t.name() == name) {
            Some(tool) => {
                match tool.execute(input.clone(), ctx).await {
                    Ok(ToolResult::Text { text }) => {
                        ContentBlock::ToolResult {
                            tool_use_id: id,
                            content: Some(vec![claude_types::message::ToolResultContent::Text {
                                text,
                            }]),
                            is_error: Some(false),
                        }
                    }
                    Ok(ToolResult::Error { text }) => {
                        warn!("Tool {} returned error: {}", name, text);
                        ContentBlock::ToolResult {
                            tool_use_id: id,
                            content: Some(vec![claude_types::message::ToolResultContent::Text {
                                text,
                            }]),
                            is_error: Some(true),
                        }
                    }
                    Err(e) => {
                        warn!("Tool {} execution failed: {}", name, e);
                        ContentBlock::ToolResult {
                            tool_use_id: id,
                            content: Some(vec![claude_types::message::ToolResultContent::Text {
                                text: format!("Tool execution error: {}", e),
                            }]),
                            is_error: Some(true),
                        }
                    }
                }
            }
            None => {
                warn!("Unknown tool requested: {}", name);
                ContentBlock::ToolResult {
                    tool_use_id: id,
                    content: Some(vec![claude_types::message::ToolResultContent::Text {
                        text: format!("Unknown tool: {}", name),
                    }]),
                    is_error: Some(true),
                }
            }
        };

        results.push(tool_result);
    }

    results
}

// ─── Main Query Loop ──────────────────────────────────────────────────────────

/// Execute the agentic query loop.
///
/// Flow:
/// 1. Build the API request from current messages + system prompt + tools
/// 2. Call the Anthropic messages API (non-streaming)
/// 3. Parse the response; append assistant message to conversation
/// 4. If the response contains `tool_use` blocks → execute tools, append
///    a `user` message with `tool_result` blocks, then repeat from step 1
/// 5. Loop until `stop_reason` is `end_turn` / `stop_sequence`, or
///    `max_iterations` is reached
pub async fn run_query(
    client: &AnthropicClient,
    tools: &[Box<dyn Tool>],
    options: QueryOptions,
) -> Result<QueryResult> {
    let mut messages = options.messages.clone();
    let mut total_usage = UsageInfo::default();
    let mut iterations = 0;
    let mut final_stop_reason = "end_turn".to_string();

    loop {
        if iterations >= options.max_iterations {
            warn!(
                "Query reached max_iterations ({}), stopping",
                options.max_iterations
            );
            final_stop_reason = "max_iterations".to_string();
            break;
        }

        // ── Step 1: Build request ────────────────────────────────────────────
        let request = build_request(&options, &messages, tools);
        debug!("API call iteration {} / {}", iterations + 1, options.max_iterations);

        // ── Step 2: Call API ─────────────────────────────────────────────────
        let response = client
            .create_message(&request)
            .await
            .context("Anthropic API call failed")?;

        iterations += 1;

        // ── Step 3: Parse response ───────────────────────────────────────────
        let stop_reason = response["stop_reason"]
            .as_str()
            .unwrap_or("end_turn")
            .to_string();

        // Accumulate usage
        if let Some(usage) = response.get("usage") {
            total_usage.accumulate(usage);
        }

        // Convert API response content to our types
        let resp_content = response["content"]
            .as_array()
            .map(|a| a.as_slice())
            .unwrap_or(&[]);

        let assistant_blocks = api_content_to_blocks(resp_content);

        // Append assistant message to conversation
        let assistant_msg = Message::Assistant(claude_types::message::AssistantMessage {
            id: Some(uuid::Uuid::new_v4()),
            role: "assistant".to_string(),
            content: assistant_blocks.clone(),
            model: response["model"].as_str().map(|s| s.to_string()),
            stop_reason: Some(stop_reason.clone()),
            usage: response.get("usage").and_then(|u| {
                Some(MessageUsage {
                    input_tokens: u["input_tokens"].as_u64()?,
                    output_tokens: u["output_tokens"].as_u64()?,
                    cache_creation_input_tokens: u["cache_creation_input_tokens"].as_u64(),
                    cache_read_input_tokens: u["cache_read_input_tokens"].as_u64(),
                })
            }),
        });
        messages.push(assistant_msg);

        // ── Step 4: Handle tool_use or stop ──────────────────────────────────
        if stop_reason == "tool_use" {
            // Collect tool_use blocks from the raw API response
            let tool_use_blocks: Vec<Value> = resp_content
                .iter()
                .filter(|c| c["type"] == "tool_use")
                .cloned()
                .collect();

            if tool_use_blocks.is_empty() {
                // Defensive: no actual tool_use blocks despite stop_reason
                warn!("stop_reason=tool_use but no tool_use blocks found, stopping");
                final_stop_reason = stop_reason;
                break;
            }

            // Execute tools
            let tool_result_blocks =
                execute_tool_uses(&tool_use_blocks, tools, &options.tool_context).await;

            // Append user message with tool results
            let user_tool_result = Message::User(claude_types::message::UserMessage {
                id: Some(uuid::Uuid::new_v4()),
                role: "user".to_string(),
                content: tool_result_blocks,
                is_meta: Some(true),
                origin: None,
            });
            messages.push(user_tool_result);

            // Continue the loop
            continue;
        }

        // ── Step 5: Terminal stop ─────────────────────────────────────────────
        final_stop_reason = stop_reason.clone();

        // "end_turn", "stop_sequence", "max_tokens" → all exit the loop
        if matches!(
            stop_reason.as_str(),
            "end_turn" | "stop_sequence" | "max_tokens"
        ) {
            break;
        }

        // Unknown stop_reason – log and break to avoid infinite loop
        warn!("Unexpected stop_reason: {}, stopping", stop_reason);
        break;
    }

    Ok(QueryResult {
        messages,
        stop_reason: final_stop_reason,
        usage: total_usage,
        iterations,
    })
}

// ─── Convenience Wrappers ─────────────────────────────────────────────────────

/// Simple single-turn query (no tools, no loop) – useful for non-agentic calls.
pub async fn query_once(
    client: &AnthropicClient,
    model: &str,
    system_prompt: Option<&str>,
    user_message: &str,
) -> Result<String> {
    let options = QueryOptions {
        model: model.to_string(),
        system_prompt: system_prompt.map(|s| s.to_string()),
        messages: vec![Message::User(claude_types::message::UserMessage {
            id: Some(uuid::Uuid::new_v4()),
            role: "user".to_string(),
            content: vec![ContentBlock::Text {
                text: user_message.to_string(),
            }],
            is_meta: None,
            origin: None,
        })],
        max_iterations: 1,
        ..Default::default()
    };

    let result = run_query(client, &[], options).await?;

    // Extract text from last assistant message
    let text = result
        .messages
        .iter()
        .rev()
        .find_map(|m| {
            if let Message::Assistant(a) = m {
                a.content.iter().find_map(|b| {
                    if let ContentBlock::Text { text } = b {
                        Some(text.clone())
                    } else {
                        None
                    }
                })
            } else {
                None
            }
        })
        .unwrap_or_default();

    Ok(text)
}

// ─── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_usage_accumulate() {
        let mut u = UsageInfo::default();
        let response_usage = json!({
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 10,
            "cache_read_input_tokens": 5,
        });
        u.accumulate(&response_usage);
        assert_eq!(u.input_tokens, 100);
        assert_eq!(u.output_tokens, 50);
        u.accumulate(&response_usage);
        assert_eq!(u.input_tokens, 200);
        assert_eq!(u.output_tokens, 100);
    }

    #[test]
    fn test_build_tools_json_empty() {
        let tools: Vec<Box<dyn Tool>> = Vec::new();
        let json = build_tools_json(&tools);
        assert!(json.is_empty());
    }

    #[test]
    fn test_content_blocks_text_roundtrip() {
        let blocks = vec![ContentBlock::Text {
            text: "Hello, world!".to_string(),
        }];
        let api = content_blocks_to_api(&blocks);
        assert_eq!(api[0]["type"], "text");
        assert_eq!(api[0]["text"], "Hello, world!");
    }

    #[test]
    fn test_content_blocks_tool_use() {
        let blocks = vec![ContentBlock::ToolUse {
            id: "toolu_01".to_string(),
            name: "bash".to_string(),
            input: json!({ "command": "ls" }),
        }];
        let api = content_blocks_to_api(&blocks);
        assert_eq!(api[0]["type"], "tool_use");
        assert_eq!(api[0]["name"], "bash");
        assert_eq!(api[0]["input"]["command"], "ls");
    }

    #[test]
    fn test_api_content_to_blocks_text() {
        let content = vec![json!({ "type": "text", "text": "Hi!" })];
        let blocks = api_content_to_blocks(&content);
        assert_eq!(blocks.len(), 1);
        assert!(matches!(&blocks[0], ContentBlock::Text { text } if text == "Hi!"));
    }

    #[test]
    fn test_api_content_to_blocks_tool_use() {
        let content = vec![json!({
            "type": "tool_use",
            "id": "toolu_42",
            "name": "read_file",
            "input": { "path": "/etc/hosts" }
        })];
        let blocks = api_content_to_blocks(&content);
        assert_eq!(blocks.len(), 1);
        if let ContentBlock::ToolUse { id, name, .. } = &blocks[0] {
            assert_eq!(id, "toolu_42");
            assert_eq!(name, "read_file");
        } else {
            panic!("Expected ToolUse block");
        }
    }

    #[test]
    fn test_messages_to_api_filters_non_chat() {
        // Tombstone messages should be skipped
        let messages = vec![
            Message::User(claude_types::message::UserMessage {
                id: None,
                role: "user".to_string(),
                content: vec![ContentBlock::Text { text: "hi".to_string() }],
                is_meta: None,
                origin: None,
            }),
        ];
        let api = messages_to_api(&messages);
        assert_eq!(api.len(), 1);
        assert_eq!(api[0]["role"], "user");
    }
}
