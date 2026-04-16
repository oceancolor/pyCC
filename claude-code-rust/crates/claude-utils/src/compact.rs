// 原始 TS: utils/compact.ts
//! 对话压缩：context 过长时截断历史

use claude_types::message::Message;

pub const MAX_CONTEXT_TOKENS: usize = 100_000;
pub const KEEP_RECENT_MESSAGES: usize = 10;

pub fn should_compact(token_count: usize) -> bool {
    token_count > MAX_CONTEXT_TOKENS
}

pub fn compact_messages(messages: Vec<Message>, keep_system: bool) -> Vec<Message> {
    // 保留 system + 最近 N 条
    todo!()
}
