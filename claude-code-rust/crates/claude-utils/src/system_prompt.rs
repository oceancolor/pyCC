// Original TS source: utils/systemPrompt.ts
// System prompt building utilities

/// A system prompt is a list of prompt strings
pub type SystemPrompt = Vec<String>;

/// Convert a list of strings to a SystemPrompt
pub fn as_system_prompt(parts: Vec<String>) -> SystemPrompt {
    parts
}

/// Options for building the effective system prompt
pub struct SystemPromptOptions {
    pub custom_system_prompt: Option<String>,
    pub default_system_prompt: Vec<String>,
    pub append_system_prompt: Option<String>,
    pub override_system_prompt: Option<String>,
    pub agent_system_prompt: Option<String>,
    pub is_coordinator_mode: bool,
}

/// Build the effective system prompt from options.
///
/// Priority order:
/// 0. Override system prompt (if set, replaces all others)
/// 1. Coordinator system prompt (if coordinator mode is active)
/// 2. Agent system prompt (if set)
/// 3. Custom system prompt
/// 4. Default system prompt
///
/// appendSystemPrompt is always appended at the end.
pub fn build_effective_system_prompt(opts: SystemPromptOptions) -> SystemPrompt {
    let mut parts = Vec::new();

    if let Some(override_prompt) = opts.override_system_prompt {
        return vec![override_prompt];
    }

    if opts.is_coordinator_mode {
        // TODO: Add coordinator system prompt
        // For now fall through to default
    }

    if let Some(agent_prompt) = opts.agent_system_prompt {
        // Agent prompt replaces default in normal mode
        parts.push(agent_prompt);
    } else if let Some(custom_prompt) = opts.custom_system_prompt {
        // Custom prompt replaces default
        parts.push(custom_prompt);
    } else {
        // Default prompt
        parts.extend(opts.default_system_prompt);
    }

    if let Some(append) = opts.append_system_prompt {
        parts.push(append);
    }

    parts
}

/// Get the base system prompt prefix for this invocation.
/// See constants/system.ts for the available prefixes.
pub fn get_base_system_prompt_prefix(
    is_non_interactive: bool,
    has_append_system_prompt: bool,
    api_provider: &str,
) -> &'static str {
    use claude_constants::system::{
        CLI_SYSPROMPT_PREFIX_DEFAULT,
        CLI_SYSPROMPT_PREFIX_AGENT_SDK,
        CLI_SYSPROMPT_PREFIX_AGENT_SDK_PRESET,
    };

    if api_provider == "vertex" {
        return CLI_SYSPROMPT_PREFIX_DEFAULT;
    }

    if is_non_interactive {
        if has_append_system_prompt {
            return CLI_SYSPROMPT_PREFIX_AGENT_SDK_PRESET;
        }
        return CLI_SYSPROMPT_PREFIX_AGENT_SDK;
    }

    CLI_SYSPROMPT_PREFIX_DEFAULT
}

/// Combine system prompt parts into a single string for API calls.
pub fn combine_system_prompt_parts(parts: &[String]) -> String {
    parts.join("\n\n")
}
