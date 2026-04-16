// Original TS source: commands/compact/
// Compact command - compress conversation context

use anyhow::Result;

pub struct CompactCommand;

impl CompactCommand {
    pub const NAME: &'static str = "compact";
    pub const DESCRIPTION: &'static str = "Compress conversation context to free up space";

    /// Compact the conversation by summarizing older messages.
    /// TODO: Full implementation requires running a summarization model call.
    pub async fn run() -> Result<String> {
        // TODO: Implement full compaction:
        // 1. Build system prompt for summarization
        // 2. Send messages to model for summarization
        // 3. Return compact result to replace old messages
        Ok("TODO: Conversation compaction not yet implemented. \
            This would summarize older messages to free context window space.".to_string())
    }
}

/// Errors for compaction operations
pub const ERROR_MESSAGE_NOT_ENOUGH_MESSAGES: &str =
    "Not enough messages to compact. Continue the conversation first.";
pub const ERROR_MESSAGE_INCOMPLETE_RESPONSE: &str =
    "The response was incomplete. Please try again.";
pub const ERROR_MESSAGE_USER_ABORT: &str =
    "Compaction aborted by user.";
