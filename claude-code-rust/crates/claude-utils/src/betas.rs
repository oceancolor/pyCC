// Original TS source: utils/betas.ts
// Beta header selection for API requests

use claude_constants::*;

/// Get beta headers for a given model and context.
/// 
/// # Arguments
/// * `model` - The model being used
/// * `has_1m_context` - Whether 1M context window is available
/// * `is_claude_ai_subscriber` - Whether using Claude.ai OAuth subscription
/// * `is_non_interactive` - Whether running in non-interactive mode
pub fn get_model_betas(
    model: &str,
    has_1m_context: bool,
    is_claude_ai_subscriber: bool,
    is_non_interactive: bool,
) -> Vec<&'static str> {
    let mut betas = vec![];

    // Always include the base Claude Code beta
    betas.push(CLAUDE_CODE_20250219_BETA_HEADER);

    // Context management
    betas.push(CONTEXT_MANAGEMENT_BETA_HEADER);

    // Interleaved thinking for claude-3-7 and newer
    if is_claude_3_7_or_newer(model) {
        betas.push(INTERLEAVED_THINKING_BETA_HEADER);
    }

    // 1M context window
    if has_1m_context {
        betas.push(CONTEXT_1M_BETA_HEADER);
    }

    // Structured outputs
    betas.push(STRUCTURED_OUTPUTS_BETA_HEADER);

    // Token efficient tools
    if supports_token_efficient_tools(model) {
        betas.push(TOKEN_EFFICIENT_TOOLS_BETA_HEADER);
    }

    // Prompt caching scope
    betas.push(PROMPT_CACHING_SCOPE_BETA_HEADER);

    // Filter out empty string betas (feature-gated)
    betas.into_iter().filter(|b| !b.is_empty()).collect()
}

/// Check if a model is claude-3-7 or newer (supports interleaved thinking).
pub fn is_claude_3_7_or_newer(model: &str) -> bool {
    model.contains("claude-3-7")
        || model.contains("claude-opus-4")
        || model.contains("claude-sonnet-4")
        || model.contains("claude-haiku-4")
}

/// Check if a model supports token-efficient tool use.
pub fn supports_token_efficient_tools(model: &str) -> bool {
    // Claude Haiku 3.5 and above support token efficient tools
    is_claude_3_7_or_newer(model)
        || model.contains("claude-3-5")
        || model.contains("claude-haiku-4-5")
}

/// Get betas that go into the request body (for Bedrock) instead of headers.
pub fn get_bedrock_extra_body_betas(betas: &[&str]) -> Vec<&str> {
    let bedrock_params = bedrock_extra_params_headers();
    betas.iter()
        .filter(|b| bedrock_params.contains(b))
        .cloned()
        .collect()
}

/// Get betas that go into request headers (for standard API).
pub fn get_header_betas(betas: &[&str]) -> Vec<&str> {
    let bedrock_params = bedrock_extra_params_headers();
    betas.iter()
        .filter(|b| !bedrock_params.contains(b))
        .cloned()
        .collect()
}
