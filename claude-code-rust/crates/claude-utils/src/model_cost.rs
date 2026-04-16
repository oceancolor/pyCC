// 原始 TS: utils/modelCost.ts
//! Model pricing and cost calculation utilities.
//!
//! Costs are in USD per million tokens (Mtok).
//! @see https://platform.claude.com/docs/en/about-claude/pricing

use std::collections::HashMap;

/// Cost structure for a model (USD per million tokens).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ModelCosts {
    pub input_tokens: f64,
    pub output_tokens: f64,
    pub prompt_cache_write_tokens: f64,
    pub prompt_cache_read_tokens: f64,
    pub web_search_requests: f64,
}

/// Usage data from an API response.
#[derive(Debug, Clone, Default)]
pub struct TokenUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_read_input_tokens: Option<u64>,
    pub cache_creation_input_tokens: Option<u64>,
    pub web_search_requests: Option<u64>,
    /// Speed hint from API: "fast" | "standard" | None
    pub speed: Option<String>,
}

// ── Pricing tiers ──────────────────────────────────────────────────────────

/// Standard pricing tier for Sonnet models: $3 input / $15 output per Mtok
pub const COST_TIER_3_15: ModelCosts = ModelCosts {
    input_tokens: 3.0,
    output_tokens: 15.0,
    prompt_cache_write_tokens: 3.75,
    prompt_cache_read_tokens: 0.3,
    web_search_requests: 0.01,
};

/// Pricing tier for Opus 4/4.1: $15 input / $75 output per Mtok
pub const COST_TIER_15_75: ModelCosts = ModelCosts {
    input_tokens: 15.0,
    output_tokens: 75.0,
    prompt_cache_write_tokens: 18.75,
    prompt_cache_read_tokens: 1.5,
    web_search_requests: 0.01,
};

/// Pricing tier for Opus 4.5: $5 input / $25 output per Mtok
pub const COST_TIER_5_25: ModelCosts = ModelCosts {
    input_tokens: 5.0,
    output_tokens: 25.0,
    prompt_cache_write_tokens: 6.25,
    prompt_cache_read_tokens: 0.5,
    web_search_requests: 0.01,
};

/// Fast mode pricing for Opus 4.6: $30 input / $150 output per Mtok
pub const COST_TIER_30_150: ModelCosts = ModelCosts {
    input_tokens: 30.0,
    output_tokens: 150.0,
    prompt_cache_write_tokens: 37.5,
    prompt_cache_read_tokens: 3.0,
    web_search_requests: 0.01,
};

/// Pricing for Haiku 3.5: $0.80 input / $4 output per Mtok
pub const COST_HAIKU_35: ModelCosts = ModelCosts {
    input_tokens: 0.8,
    output_tokens: 4.0,
    prompt_cache_write_tokens: 1.0,
    prompt_cache_read_tokens: 0.08,
    web_search_requests: 0.01,
};

/// Pricing for Haiku 4.5: $1 input / $5 output per Mtok
pub const COST_HAIKU_45: ModelCosts = ModelCosts {
    input_tokens: 1.0,
    output_tokens: 5.0,
    prompt_cache_write_tokens: 1.25,
    prompt_cache_read_tokens: 0.1,
    web_search_requests: 0.01,
};

const DEFAULT_UNKNOWN_MODEL_COST: ModelCosts = COST_TIER_5_25;

// ── Model cost table ───────────────────────────────────────────────────────

/// Build a map of canonical model short-name → cost tier.
/// Keys are normalized lowercase canonical names.
pub fn build_model_costs() -> HashMap<&'static str, ModelCosts> {
    let mut m = HashMap::new();
    // claude-3-5-haiku
    m.insert("claude-3-5-haiku", COST_HAIKU_35);
    // claude-haiku-4-5
    m.insert("claude-haiku-4-5", COST_HAIKU_45);
    // claude-3-5-sonnet / claude-3-5-v2-sonnet
    m.insert("claude-3-5-sonnet", COST_TIER_3_15);
    m.insert("claude-3-5-v2-sonnet", COST_TIER_3_15);
    // claude-3-7-sonnet
    m.insert("claude-3-7-sonnet", COST_TIER_3_15);
    // claude-sonnet-4
    m.insert("claude-sonnet-4", COST_TIER_3_15);
    m.insert("claude-sonnet-4-5", COST_TIER_3_15);
    m.insert("claude-sonnet-4-6", COST_TIER_3_15);
    // claude-opus-4 / 4.1
    m.insert("claude-opus-4", COST_TIER_15_75);
    m.insert("claude-opus-4-1", COST_TIER_15_75);
    // claude-opus-4.5 / 4.6
    m.insert("claude-opus-4-5", COST_TIER_5_25);
    m.insert("claude-opus-4-6", COST_TIER_5_25);
    m
}

lazy_static::lazy_static! {
    static ref MODEL_COSTS: HashMap<&'static str, ModelCosts> = build_model_costs();
}

/// Normalize a model name to a canonical short name.
/// Strips date suffixes like -20241022 and lowercases.
pub fn get_canonical_name(model: &str) -> String {
    let s = model.to_lowercase();
    // Strip date suffix patterns like -20241022, -latest, etc.
    // Simple heuristic: strip trailing -YYYYMMDD
    if let Some(idx) = s.rfind('-') {
        let suffix = &s[idx + 1..];
        if suffix.len() == 8 && suffix.chars().all(|c| c.is_ascii_digit()) {
            return s[..idx].to_string();
        }
    }
    s
}

/// Get the cost tier for Opus 4.6 based on fast mode.
pub fn get_opus46_cost_tier(is_fast_mode: bool) -> ModelCosts {
    if is_fast_mode {
        COST_TIER_30_150
    } else {
        COST_TIER_5_25
    }
}

/// Get the ModelCosts for a given model name and usage.
pub fn get_model_costs(model: &str, usage: &TokenUsage) -> ModelCosts {
    let canonical = get_canonical_name(model);

    // Special case: Opus 4.6 has dynamic fast-mode pricing
    if canonical == "claude-opus-4-6" {
        let is_fast = usage.speed.as_deref() == Some("fast");
        return get_opus46_cost_tier(is_fast);
    }

    MODEL_COSTS
        .get(canonical.as_str())
        .copied()
        .unwrap_or(DEFAULT_UNKNOWN_MODEL_COST)
}

/// Calculate USD cost from token usage and model.
pub fn calculate_usd_cost(model: &str, usage: &TokenUsage) -> f64 {
    let costs = get_model_costs(model, usage);
    tokens_to_usd_cost(&costs, usage)
}

/// Convert token counts to USD using model costs.
pub fn tokens_to_usd_cost(costs: &ModelCosts, usage: &TokenUsage) -> f64 {
    let input_cost = (usage.input_tokens as f64 / 1_000_000.0) * costs.input_tokens;
    let output_cost = (usage.output_tokens as f64 / 1_000_000.0) * costs.output_tokens;
    let cache_read_cost = (usage.cache_read_input_tokens.unwrap_or(0) as f64 / 1_000_000.0)
        * costs.prompt_cache_read_tokens;
    let cache_write_cost = (usage.cache_creation_input_tokens.unwrap_or(0) as f64 / 1_000_000.0)
        * costs.prompt_cache_write_tokens;
    let web_search_cost =
        (usage.web_search_requests.unwrap_or(0) as f64) * costs.web_search_requests;

    input_cost + output_cost + cache_read_cost + cache_write_cost + web_search_cost
}

/// Calculate cost from raw token counts without a full usage object.
pub fn calculate_cost_from_tokens(
    model: &str,
    input_tokens: u64,
    output_tokens: u64,
    cache_read_input_tokens: u64,
    cache_creation_input_tokens: u64,
) -> f64 {
    let usage = TokenUsage {
        input_tokens,
        output_tokens,
        cache_read_input_tokens: Some(cache_read_input_tokens),
        cache_creation_input_tokens: Some(cache_creation_input_tokens),
        ..Default::default()
    };
    calculate_usd_cost(model, &usage)
}

fn format_price(price: f64) -> String {
    if price.fract() == 0.0 {
        format!("${}", price as i64)
    } else {
        format!("${:.2}", price)
    }
}

/// Format model costs as a pricing string, e.g., "$3/$15 per Mtok"
pub fn format_model_pricing(costs: &ModelCosts) -> String {
    format!(
        "{}/{} per Mtok",
        format_price(costs.input_tokens),
        format_price(costs.output_tokens)
    )
}

/// Get a formatted pricing string for a model name.
pub fn get_model_pricing_string(model: &str) -> Option<String> {
    let canonical = get_canonical_name(model);
    MODEL_COSTS
        .get(canonical.as_str())
        .map(|c| format_model_pricing(c))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_canonical_name() {
        assert_eq!(get_canonical_name("claude-3-5-haiku-20241022"), "claude-3-5-haiku");
        assert_eq!(get_canonical_name("claude-opus-4"), "claude-opus-4");
        assert_eq!(get_canonical_name("Claude-Sonnet-4"), "claude-sonnet-4");
    }

    #[test]
    fn test_calculate_usd_cost() {
        let usage = TokenUsage {
            input_tokens: 1_000_000,
            output_tokens: 1_000_000,
            ..Default::default()
        };
        let cost = calculate_usd_cost("claude-sonnet-4", &usage);
        // $3 input + $15 output = $18
        assert!((cost - 18.0).abs() < 0.001);
    }

    #[test]
    fn test_format_price() {
        assert_eq!(format_price(3.0), "$3");
        assert_eq!(format_price(0.8), "$0.80");
        assert_eq!(format_price(15.0), "$15");
    }

    #[test]
    fn test_opus_4_6_fast_mode() {
        let usage_fast = TokenUsage {
            input_tokens: 1_000_000,
            output_tokens: 1_000_000,
            speed: Some("fast".to_string()),
            ..Default::default()
        };
        let usage_normal = TokenUsage {
            input_tokens: 1_000_000,
            output_tokens: 1_000_000,
            ..Default::default()
        };
        let fast_cost = calculate_usd_cost("claude-opus-4-6", &usage_fast);
        let normal_cost = calculate_usd_cost("claude-opus-4-6", &usage_normal);
        // Fast: $30 + $150 = $180; Normal: $5 + $25 = $30
        assert!((fast_cost - 180.0).abs() < 0.001);
        assert!((normal_cost - 30.0).abs() < 0.001);
    }
}
