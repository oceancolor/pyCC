// Original TS source: constants/betas.ts
// Anthropic API beta headers

pub const CLAUDE_CODE_20250219_BETA_HEADER: &str = "claude-code-20250219";
pub const INTERLEAVED_THINKING_BETA_HEADER: &str = "interleaved-thinking-2025-05-14";
pub const CONTEXT_1M_BETA_HEADER: &str = "context-1m-2025-08-07";
pub const CONTEXT_MANAGEMENT_BETA_HEADER: &str = "context-management-2025-06-27";
pub const STRUCTURED_OUTPUTS_BETA_HEADER: &str = "structured-outputs-2025-12-15";
pub const WEB_SEARCH_BETA_HEADER: &str = "web-search-2025-03-05";
pub const TOOL_SEARCH_BETA_HEADER_1P: &str = "advanced-tool-use-2025-11-20";
pub const TOOL_SEARCH_BETA_HEADER_3P: &str = "tool-search-tool-2025-10-19";
pub const EFFORT_BETA_HEADER: &str = "effort-2025-11-24";
pub const TASK_BUDGETS_BETA_HEADER: &str = "task-budgets-2026-03-13";
pub const PROMPT_CACHING_SCOPE_BETA_HEADER: &str = "prompt-caching-scope-2026-01-05";
pub const FAST_MODE_BETA_HEADER: &str = "fast-mode-2026-02-01";
pub const REDACT_THINKING_BETA_HEADER: &str = "redact-thinking-2026-02-12";
pub const TOKEN_EFFICIENT_TOOLS_BETA_HEADER: &str = "token-efficient-tools-2026-03-28";
pub const ADVISOR_BETA_HEADER: &str = "advisor-tool-2026-03-01";

// Feature-gated headers (empty string = disabled at compile time by default)
// TODO: These may be enabled via runtime feature flags
pub const SUMMARIZE_CONNECTOR_TEXT_BETA_HEADER: &str = ""; // feature-gated
pub const AFK_MODE_BETA_HEADER: &str = "";                 // feature-gated
pub const CLI_INTERNAL_BETA_HEADER: &str = "";             // user_type=ant only

/// Beta headers that should go in Bedrock extraBodyParams instead of headers.
pub fn bedrock_extra_params_headers() -> &'static [&'static str] {
    &[
        INTERLEAVED_THINKING_BETA_HEADER,
        CONTEXT_1M_BETA_HEADER,
        TOOL_SEARCH_BETA_HEADER_3P,
    ]
}

/// Betas allowed on Vertex countTokens API.
pub fn vertex_count_tokens_allowed_betas() -> &'static [&'static str] {
    &[
        CLAUDE_CODE_20250219_BETA_HEADER,
        INTERLEAVED_THINKING_BETA_HEADER,
        CONTEXT_MANAGEMENT_BETA_HEADER,
    ]
}
