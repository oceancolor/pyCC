// Original TS source: utils/tokens.ts
// Token counting and context window management

use claude_types::message::{Message, MessageUsage};

/// Get the token usage from an assistant message (if present and non-synthetic).
pub fn get_token_usage(message: &Message) -> Option<&MessageUsage> {
    match message {
        Message::Assistant(m) => m.usage.as_ref(),
        _ => None,
    }
}

/// Calculate total context window tokens from a usage object.
/// Includes input_tokens + cache tokens + output_tokens.
pub fn get_token_count_from_usage(usage: &MessageUsage) -> u64 {
    usage.input_tokens
        + usage.cache_creation_input_tokens.unwrap_or(0)
        + usage.cache_read_input_tokens.unwrap_or(0)
        + usage.output_tokens
}

/// Get the token count from the most recent API response in a message list.
pub fn token_count_from_last_api_response(messages: &[Message]) -> u64 {
    for message in messages.iter().rev() {
        if let Some(usage) = get_token_usage(message) {
            return get_token_count_from_usage(usage);
        }
    }
    0
}

/// Estimate token count from messages using rough heuristics.
/// Falls back to JSON serialization if no usage data available.
pub fn estimate_token_count(messages: &[Message]) -> u64 {
    // First try to get from actual usage
    let from_usage = token_count_from_last_api_response(messages);
    if from_usage > 0 {
        return from_usage;
    }

    // Rough estimate: 4 chars ≈ 1 token
    let json = serde_json::to_string(messages).unwrap_or_default();
    (json.len() as f64 / 4.0).ceil() as u64
}

/// Get the length of assistant message content in characters.
pub fn get_assistant_message_content_length(message: &Message) -> usize {
    match message {
        Message::Assistant(m) => {
            m.content.iter().map(|block| {
                match block {
                    claude_types::message::ContentBlock::Text { text } => text.len(),
                    _ => 0,
                }
            }).sum()
        }
        _ => 0,
    }
}

/// Check if we're approaching the context window limit.
pub fn is_near_context_limit(token_count: u64, context_window: u64) -> bool {
    let ratio = token_count as f64 / context_window as f64;
    ratio >= 0.75
}

/// Get the remaining token budget.
pub fn remaining_token_budget(token_count: u64, context_window: u64) -> i64 {
    context_window as i64 - token_count as i64
}
