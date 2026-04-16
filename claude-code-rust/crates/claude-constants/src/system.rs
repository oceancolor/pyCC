// Original TS source: constants/system.ts
// System prompt prefix constants and attribution header helpers

/// CLI system prompt prefixes
pub const CLI_SYSPROMPT_PREFIX_DEFAULT: &str = "You are Claude Code, Anthropic's official CLI for Claude.";
pub const CLI_SYSPROMPT_PREFIX_AGENT_SDK_PRESET: &str = "You are Claude Code, Anthropic's official CLI for Claude, running within the Claude Agent SDK.";
pub const CLI_SYSPROMPT_PREFIX_AGENT_SDK: &str = "You are a Claude agent, built on Anthropic's Claude Agent SDK.";

/// All possible CLI sysprompt prefixes
pub const CLI_SYSPROMPT_PREFIXES: &[&str] = &[
    CLI_SYSPROMPT_PREFIX_DEFAULT,
    CLI_SYSPROMPT_PREFIX_AGENT_SDK_PRESET,
    CLI_SYSPROMPT_PREFIX_AGENT_SDK,
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CLISyspromptPrefix {
    Default,
    AgentSdkPreset,
    AgentSdk,
}

impl CLISyspromptPrefix {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Default => CLI_SYSPROMPT_PREFIX_DEFAULT,
            Self::AgentSdkPreset => CLI_SYSPROMPT_PREFIX_AGENT_SDK_PRESET,
            Self::AgentSdk => CLI_SYSPROMPT_PREFIX_AGENT_SDK,
        }
    }
}

/// API provider type
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ApiProvider {
    Anthropic,
    Vertex,
    Bedrock,
}

/// Get the CLI sysprompt prefix based on context.
pub fn get_cli_sysprompt_prefix(
    api_provider: &ApiProvider,
    is_non_interactive: bool,
    has_append_system_prompt: bool,
) -> CLISyspromptPrefix {
    if *api_provider == ApiProvider::Vertex {
        return CLISyspromptPrefix::Default;
    }
    if is_non_interactive {
        if has_append_system_prompt {
            return CLISyspromptPrefix::AgentSdkPreset;
        }
        return CLISyspromptPrefix::AgentSdk;
    }
    CLISyspromptPrefix::Default
}

/// Build an attribution header for API requests.
///
/// # Arguments
/// * `fingerprint` - Version fingerprint
/// * `entrypoint` - The entrypoint name (from CLAUDE_CODE_ENTRYPOINT env var)
/// * `workload` - Optional workload tag
/// * `native_attestation` - Whether to include cch placeholder
pub fn build_attribution_header(
    fingerprint: &str,
    entrypoint: &str,
    workload: Option<&str>,
    native_attestation: bool,
    version: &str,
) -> String {
    let full_version = format!("{}.{}", version, fingerprint);
    let cch = if native_attestation { " cch=00000;" } else { "" };
    let workload_pair = if let Some(w) = workload {
        format!(" cc_workload={};", w)
    } else {
        String::new()
    };
    format!(
        "x-anthropic-billing-header: cc_version={}; cc_entrypoint={};{}{}",
        full_version, entrypoint, cch, workload_pair
    )
}
