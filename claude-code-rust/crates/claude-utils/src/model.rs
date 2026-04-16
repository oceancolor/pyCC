// Original TS source: utils/model/configs.ts, aliases.ts, model.ts
// Model configuration and selection

use std::collections::HashMap;
use once_cell::sync::Lazy;

// ============================================================================
// API Provider
// ============================================================================

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum ApiProvider {
    FirstParty,
    Bedrock,
    Vertex,
    Foundry,
}

// ============================================================================
// Model Config
// ============================================================================

#[derive(Debug, Clone)]
pub struct ModelConfig {
    pub first_party: &'static str,
    pub bedrock: &'static str,
    pub vertex: &'static str,
    pub foundry: &'static str,
}

impl ModelConfig {
    pub fn for_provider(&self, provider: &ApiProvider) -> &str {
        match provider {
            ApiProvider::FirstParty => self.first_party,
            ApiProvider::Bedrock => self.bedrock,
            ApiProvider::Vertex => self.vertex,
            ApiProvider::Foundry => self.foundry,
        }
    }
}

// ============================================================================
// All Model Configs
// ============================================================================

// @[MODEL LAUNCH]: Add new model config here

pub const CLAUDE_3_5_HAIKU_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-3-5-haiku-20241022",
    bedrock: "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    vertex: "claude-3-5-haiku@20241022",
    foundry: "claude-3-5-haiku",
};

pub const CLAUDE_HAIKU_4_5_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-haiku-4-5-20251001",
    bedrock: "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    vertex: "claude-haiku-4-5@20251001",
    foundry: "claude-haiku-4-5",
};

pub const CLAUDE_3_5_V2_SONNET_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-3-5-sonnet-20241022",
    bedrock: "anthropic.claude-3-5-sonnet-20241022-v2:0",
    vertex: "claude-3-5-sonnet-v2@20241022",
    foundry: "claude-3-5-sonnet",
};

pub const CLAUDE_3_7_SONNET_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-3-7-sonnet-20250219",
    bedrock: "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    vertex: "claude-3-7-sonnet@20250219",
    foundry: "claude-3-7-sonnet",
};

pub const CLAUDE_SONNET_4_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-sonnet-4-20250514",
    bedrock: "us.anthropic.claude-sonnet-4-20250514-v1:0",
    vertex: "claude-sonnet-4@20250514",
    foundry: "claude-sonnet-4",
};

pub const CLAUDE_SONNET_4_5_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-sonnet-4-5-20250929",
    bedrock: "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    vertex: "claude-sonnet-4-5@20250929",
    foundry: "claude-sonnet-4-5",
};

pub const CLAUDE_SONNET_4_6_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-sonnet-4-6",
    bedrock: "us.anthropic.claude-sonnet-4-6",
    vertex: "claude-sonnet-4-6",
    foundry: "claude-sonnet-4-6",
};

pub const CLAUDE_OPUS_4_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-opus-4-20250514",
    bedrock: "us.anthropic.claude-opus-4-20250514-v1:0",
    vertex: "claude-opus-4@20250514",
    foundry: "claude-opus-4",
};

pub const CLAUDE_OPUS_4_1_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-opus-4-1-20250805",
    bedrock: "us.anthropic.claude-opus-4-1-20250805-v1:0",
    vertex: "claude-opus-4-1@20250805",
    foundry: "claude-opus-4-1",
};

pub const CLAUDE_OPUS_4_5_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-opus-4-5-20251101",
    bedrock: "us.anthropic.claude-opus-4-5-20251101-v1:0",
    vertex: "claude-opus-4-5@20251101",
    foundry: "claude-opus-4-5",
};

pub const CLAUDE_OPUS_4_6_CONFIG: ModelConfig = ModelConfig {
    first_party: "claude-opus-4-6",
    bedrock: "us.anthropic.claude-opus-4-6-v1",
    vertex: "claude-opus-4-6",
    foundry: "claude-opus-4-6",
};

/// All model configurations, keyed by short name.
pub static ALL_MODEL_CONFIGS: Lazy<HashMap<&'static str, &'static ModelConfig>> = Lazy::new(|| {
    let mut m = HashMap::new();
    m.insert("haiku35", &CLAUDE_3_5_HAIKU_CONFIG);
    m.insert("haiku45", &CLAUDE_HAIKU_4_5_CONFIG);
    m.insert("sonnet35", &CLAUDE_3_5_V2_SONNET_CONFIG);
    m.insert("sonnet37", &CLAUDE_3_7_SONNET_CONFIG);
    m.insert("sonnet40", &CLAUDE_SONNET_4_CONFIG);
    m.insert("sonnet45", &CLAUDE_SONNET_4_5_CONFIG);
    m.insert("sonnet46", &CLAUDE_SONNET_4_6_CONFIG);
    m.insert("opus40", &CLAUDE_OPUS_4_CONFIG);
    m.insert("opus41", &CLAUDE_OPUS_4_1_CONFIG);
    m.insert("opus45", &CLAUDE_OPUS_4_5_CONFIG);
    m.insert("opus46", &CLAUDE_OPUS_4_6_CONFIG);
    m
});

// ============================================================================
// Model Aliases
// ============================================================================

pub const MODEL_ALIASES: &[&str] = &[
    "sonnet", "opus", "haiku", "best", "sonnet[1m]", "opus[1m]", "opusplan",
];

pub const MODEL_FAMILY_ALIASES: &[&str] = &["sonnet", "opus", "haiku"];

pub fn is_model_alias(model: &str) -> bool {
    MODEL_ALIASES.contains(&model)
}

pub fn is_model_family_alias(model: &str) -> bool {
    MODEL_FAMILY_ALIASES.contains(&model)
}

// ============================================================================
// Model Selection
// ============================================================================

/// Get the small/fast model name.
pub fn get_small_fast_model() -> String {
    std::env::var("ANTHROPIC_SMALL_FAST_MODEL")
        .unwrap_or_else(|_| CLAUDE_3_5_HAIKU_CONFIG.first_party.to_string())
}

/// Get the default haiku model.
pub fn get_default_haiku_model() -> &'static str {
    CLAUDE_HAIKU_4_5_CONFIG.first_party
}

/// Get the default opus model.
pub fn get_default_opus_model() -> &'static str {
    CLAUDE_OPUS_4_6_CONFIG.first_party
}

/// Get the default sonnet model.
pub fn get_default_sonnet_model() -> &'static str {
    CLAUDE_SONNET_4_6_CONFIG.first_party
}

/// Resolve a model alias to a concrete model name.
pub fn resolve_model_alias(alias: &str, provider: &ApiProvider) -> Option<String> {
    match alias {
        "haiku" => Some(get_default_haiku_model().to_string()),
        "sonnet" => Some(get_default_sonnet_model().to_string()),
        "opus" | "best" => Some(get_default_opus_model().to_string()),
        "sonnet[1m]" => Some(CLAUDE_SONNET_4_6_CONFIG.first_party.to_string()),
        "opus[1m]" => Some(CLAUDE_OPUS_4_6_CONFIG.first_party.to_string()),
        _ => None,
    }
}

/// Get model string for a given provider.
pub fn get_model_string_for_provider(model: &str, provider: &ApiProvider) -> String {
    // Check if it's already a known model alias
    if let Some(resolved) = resolve_model_alias(model, provider) {
        return resolved;
    }

    // Check if it's a canonical first-party model ID
    for config in ALL_MODEL_CONFIGS.values() {
        if config.first_party == model {
            return config.for_provider(provider).to_string();
        }
    }

    // Return as-is if unknown
    model.to_string()
}
