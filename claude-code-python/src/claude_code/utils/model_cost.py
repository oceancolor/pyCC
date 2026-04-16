"""
Python port of utils/modelCost.ts
Source: claude-code-source/utils/modelCost.ts (231 lines)

Model pricing lookup and cost calculation utilities.
Pricing reference: https://platform.claude.com/docs/en/about-claude/pricing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelCosts:
    """Cost tier for a Claude model (USD per million tokens)."""
    input_tokens: float
    output_tokens: float
    prompt_cache_write_tokens: float
    prompt_cache_read_tokens: float
    web_search_requests: float  # USD per request


@dataclass
class TokenUsage:
    """Token usage data from an API response."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    web_search_requests: int = 0
    speed: Optional[str] = None  # 'fast' | 'standard' | None


# ---------------------------------------------------------------------------
# Pricing tiers (USD per million tokens unless noted)
# ---------------------------------------------------------------------------

# Standard tier: $3 input / $15 output per Mtok (Sonnet models)
COST_TIER_3_15 = ModelCosts(
    input_tokens=3,
    output_tokens=15,
    prompt_cache_write_tokens=3.75,
    prompt_cache_read_tokens=0.3,
    web_search_requests=0.01,
)

# Opus 4 / 4.1: $15 input / $75 output per Mtok
COST_TIER_15_75 = ModelCosts(
    input_tokens=15,
    output_tokens=75,
    prompt_cache_write_tokens=18.75,
    prompt_cache_read_tokens=1.5,
    web_search_requests=0.01,
)

# Opus 4.5: $5 input / $25 output per Mtok
COST_TIER_5_25 = ModelCosts(
    input_tokens=5,
    output_tokens=25,
    prompt_cache_write_tokens=6.25,
    prompt_cache_read_tokens=0.5,
    web_search_requests=0.01,
)

# Fast mode for Opus 4.6: $30 input / $150 output per Mtok
COST_TIER_30_150 = ModelCosts(
    input_tokens=30,
    output_tokens=150,
    prompt_cache_write_tokens=37.5,
    prompt_cache_read_tokens=3,
    web_search_requests=0.01,
)

# Haiku 3.5: $0.80 input / $4 output per Mtok
COST_HAIKU_35 = ModelCosts(
    input_tokens=0.8,
    output_tokens=4,
    prompt_cache_write_tokens=1,
    prompt_cache_read_tokens=0.08,
    web_search_requests=0.01,
)

# Haiku 4.5: $1 input / $5 output per Mtok
COST_HAIKU_45 = ModelCosts(
    input_tokens=1,
    output_tokens=5,
    prompt_cache_write_tokens=1.25,
    prompt_cache_read_tokens=0.1,
    web_search_requests=0.01,
)

DEFAULT_UNKNOWN_MODEL_COST = COST_TIER_5_25

# ---------------------------------------------------------------------------
# Model name → pricing table
# Keys are canonical model short-names (lowercased model family strings).
# These mirror the TypeScript MODEL_COSTS record.
# ---------------------------------------------------------------------------

MODEL_COSTS: dict[str, ModelCosts] = {
    # Haiku family
    "claude-3-5-haiku": COST_HAIKU_35,
    "claude-3-haiku": COST_HAIKU_35,
    "claude-haiku-4-5": COST_HAIKU_45,
    "claude-haiku-4": COST_HAIKU_45,

    # Sonnet family
    "claude-3-5-sonnet": COST_TIER_3_15,
    "claude-3-5-sonnet-v2": COST_TIER_3_15,
    "claude-3-7-sonnet": COST_TIER_3_15,
    "claude-sonnet-4": COST_TIER_3_15,
    "claude-sonnet-4-5": COST_TIER_3_15,
    "claude-sonnet-4-6": COST_TIER_3_15,

    # Opus family
    "claude-opus-4": COST_TIER_15_75,
    "claude-opus-4-1": COST_TIER_15_75,
    "claude-opus-4-5": COST_TIER_5_25,
    "claude-opus-4-6": COST_TIER_5_25,  # fast mode handled separately
}


def _get_canonical_name(model: str) -> str:
    """
    Derive a canonical short name from a full model string.
    Strips version suffixes like -20240620, :beta, @latest, etc.
    """
    # lower case
    name = model.lower().strip()

    # Strip @latest, :beta, etc.
    for suffix in ("@latest", ":beta", ":latest"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]

    # Strip date suffixes like -20240620
    import re
    name = re.sub(r"-\d{8}$", "", name)

    # Normalize double dashes
    name = re.sub(r"--+", "-", name)

    return name


def get_opus_46_cost_tier(fast_mode: bool) -> ModelCosts:
    """Return the cost tier for Opus 4.6 based on fast mode."""
    if fast_mode:
        return COST_TIER_30_150
    return COST_TIER_5_25


def get_model_costs(model: str, usage: Optional[TokenUsage] = None) -> ModelCosts:
    """
    Return the ModelCosts for the given model name.

    Falls back to DEFAULT_UNKNOWN_MODEL_COST when the model is not recognized.
    Handles Opus 4.6 fast-mode pricing when usage carries speed='fast'.
    """
    canonical = _get_canonical_name(model)

    # Opus 4.6 fast mode check
    if canonical in ("claude-opus-4-6",):
        is_fast = bool(usage and usage.speed == "fast")
        return get_opus_46_cost_tier(is_fast)

    costs = MODEL_COSTS.get(canonical)
    if costs is not None:
        return costs

    # Fuzzy match: check if any known key is a prefix of the canonical name
    for key, tier in MODEL_COSTS.items():
        if canonical.startswith(key):
            return tier

    return DEFAULT_UNKNOWN_MODEL_COST


def tokens_to_usd_cost(model_costs: ModelCosts, usage: TokenUsage) -> float:
    """Calculate USD cost from token usage and model cost configuration."""
    return (
        (usage.input_tokens / 1_000_000) * model_costs.input_tokens
        + (usage.output_tokens / 1_000_000) * model_costs.output_tokens
        + (usage.cache_read_input_tokens / 1_000_000) * model_costs.prompt_cache_read_tokens
        + (usage.cache_creation_input_tokens / 1_000_000) * model_costs.prompt_cache_write_tokens
        + usage.web_search_requests * model_costs.web_search_requests
    )


def calculate_usd_cost(resolved_model: str, usage: TokenUsage) -> float:
    """Calculate the USD cost for the given model and usage."""
    model_costs = get_model_costs(resolved_model, usage)
    return tokens_to_usd_cost(model_costs, usage)


def calculate_cost_from_tokens(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> float:
    """
    Calculate cost from raw token counts without a full TokenUsage object.
    Useful for side queries that track token counts independently.
    """
    usage = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
    )
    return calculate_usd_cost(model, usage)


def _format_price(price: float) -> str:
    """Format a price: integers without decimals, others with 2 decimal places."""
    if price == int(price):
        return f"${int(price)}"
    return f"${price:.2f}"


def format_model_pricing(costs: ModelCosts) -> str:
    """Format model costs as a pricing string, e.g. '$3/$15 per Mtok'."""
    return f"{_format_price(costs.input_tokens)}/{_format_price(costs.output_tokens)} per Mtok"


def get_model_pricing_string(model: str) -> Optional[str]:
    """
    Get a formatted pricing string for a model.
    Returns None if the model is not found in the pricing table.
    """
    canonical = _get_canonical_name(model)
    costs = MODEL_COSTS.get(canonical)
    if costs is None:
        # Try prefix match
        for key, tier in MODEL_COSTS.items():
            if canonical.startswith(key):
                return format_model_pricing(tier)
        return None
    return format_model_pricing(costs)
