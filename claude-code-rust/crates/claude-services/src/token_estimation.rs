// Original TS source: services/tokenEstimation.ts
// Token estimation/counting service

use anyhow::Result;
use serde_json::Value;
use crate::api::AnthropicClient;

/// Minimum values for token counting with thinking enabled
pub const TOKEN_COUNT_THINKING_BUDGET: u64 = 1024;
pub const TOKEN_COUNT_MAX_TOKENS: u64 = 2048;

/// Check if messages contain thinking blocks
pub fn has_thinking_blocks(messages: &[Value]) -> bool {
    for msg in messages {
        if msg["role"] == "assistant" {
            if let Some(content) = msg["content"].as_array() {
                for block in content {
                    let block_type = block["type"].as_str().unwrap_or_default();
                    if block_type == "thinking" || block_type == "redacted_thinking" {
                        return true;
                    }
                }
            }
        }
    }
    false
}

/// Count tokens for a given set of messages and model.
pub async fn count_tokens(
    client: &AnthropicClient,
    model: &str,
    messages: &[Value],
    system: Option<&str>,
    tools: Option<&[Value]>,
) -> Result<u64> {
    let mut request = serde_json::json!({
        "model": model,
        "messages": messages,
    });

    if let Some(sys) = system {
        request["system"] = serde_json::json!(sys);
    }

    if let Some(t) = tools {
        request["tools"] = serde_json::json!(t);
    }

    // If messages contain thinking blocks, add the required thinking params
    if has_thinking_blocks(messages) {
        request["thinking"] = serde_json::json!({
            "type": "enabled",
            "budget_tokens": TOKEN_COUNT_THINKING_BUDGET
        });
        request["max_tokens"] = serde_json::json!(TOKEN_COUNT_MAX_TOKENS);
    }

    client.count_tokens(&request).await
}

/// Rough token estimation based on character count.
/// 1 token ≈ 4 characters for English text.
pub fn estimate_tokens(text: &str) -> u64 {
    (text.len() as f64 / 4.0).ceil() as u64
}

/// Estimate tokens for a JSON value.
pub fn estimate_tokens_json(value: &Value) -> u64 {
    let serialized = serde_json::to_string(value).unwrap_or_default();
    estimate_tokens(&serialized)
}
