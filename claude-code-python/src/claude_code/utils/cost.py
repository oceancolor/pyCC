# 原始 TS: utils/modelCost.ts, cost-tracker.ts
"""
Token cost calculation utilities.
Tracks API usage costs across a session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelCosts:
    """Per-million-token pricing for a model."""
    input_tokens: float         # $ per million input tokens
    output_tokens: float        # $ per million output tokens
    prompt_cache_write_tokens: float = 0.0
    prompt_cache_read_tokens: float = 0.0
    web_search_requests: float = 0.0  # $ per request


# Standard pricing tiers (USD per million tokens)
COST_TIER_3_15 = ModelCosts(
    input_tokens=3.0,
    output_tokens=15.0,
    prompt_cache_write_tokens=3.75,
    prompt_cache_read_tokens=0.3,
    web_search_requests=0.01,
)

COST_TIER_15_75 = ModelCosts(
    input_tokens=15.0,
    output_tokens=75.0,
    prompt_cache_write_tokens=18.75,
    prompt_cache_read_tokens=1.5,
    web_search_requests=0.01,
)

COST_TIER_5_25 = ModelCosts(
    input_tokens=5.0,
    output_tokens=25.0,
    prompt_cache_write_tokens=6.25,
    prompt_cache_read_tokens=0.5,
    web_search_requests=0.01,
)

COST_HAIKU_35 = ModelCosts(
    input_tokens=0.8,
    output_tokens=4.0,
    prompt_cache_write_tokens=1.0,
    prompt_cache_read_tokens=0.08,
    web_search_requests=0.01,
)

COST_HAIKU_45 = ModelCosts(
    input_tokens=1.0,
    output_tokens=5.0,
    prompt_cache_write_tokens=1.25,
    prompt_cache_read_tokens=0.1,
    web_search_requests=0.01,
)

DEFAULT_UNKNOWN_MODEL_COST = COST_TIER_5_25

# Model name → pricing tier mapping
# Model names are simplified for Python port (canonical short names)
MODEL_COSTS: dict[str, ModelCosts] = {
    # Claude 3.5 family
    "claude-3-5-haiku": COST_HAIKU_35,
    "claude-haiku-4-5": COST_HAIKU_45,
    "claude-3-5-sonnet": COST_TIER_3_15,
    "claude-3-7-sonnet": COST_TIER_3_15,
    # Claude 4 family
    "claude-sonnet-4": COST_TIER_3_15,
    "claude-sonnet-4-5": COST_TIER_3_15,
    "claude-sonnet-4-6": COST_TIER_3_15,
    "claude-opus-4": COST_TIER_15_75,
    "claude-opus-4-1": COST_TIER_15_75,
    "claude-opus-4-5": COST_TIER_5_25,
    "claude-opus-4-6": COST_TIER_5_25,
}


def get_model_costs(model_name: str) -> ModelCosts:
    """
    Get the cost tier for a model.
    Returns DEFAULT_UNKNOWN_MODEL_COST if model is not recognized.
    """
    # Try exact match first
    if model_name in MODEL_COSTS:
        return MODEL_COSTS[model_name]

    # Try prefix matching (e.g., "claude-3-5-sonnet-20241022" → "claude-3-5-sonnet")
    model_lower = model_name.lower()
    for key in MODEL_COSTS:
        if model_lower.startswith(key) or key in model_lower:
            return MODEL_COSTS[key]

    return DEFAULT_UNKNOWN_MODEL_COST


def calculate_usd_cost(
    model_name: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    web_search_requests: int = 0,
) -> float:
    """
    Calculate the USD cost for a given set of token counts.
    原始 TS: calculateUSDCost()
    
    Returns cost in USD.
    """
    costs = get_model_costs(model_name)
    
    # Per-million token pricing
    total = (
        (input_tokens * costs.input_tokens / 1_000_000) +
        (output_tokens * costs.output_tokens / 1_000_000) +
        (cache_write_tokens * costs.prompt_cache_write_tokens / 1_000_000) +
        (cache_read_tokens * costs.prompt_cache_read_tokens / 1_000_000) +
        (web_search_requests * costs.web_search_requests)
    )
    return total


@dataclass
class UsageRecord:
    """Usage record for a single API call."""
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    web_search_requests: int = 0
    api_duration_ms: int = 0
    cost_usd: float = 0.0


@dataclass
class SessionCostTracker:
    """
    Tracks cumulative API costs for a session.
    原始 TS: cost-tracker.ts (global state → Python class)
    """
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_web_search_requests: int = 0
    total_api_duration_ms: int = 0
    total_tool_duration_ms: int = 0
    total_lines_added: int = 0
    total_lines_removed: int = 0
    model_usage: dict[str, UsageRecord] = field(default_factory=dict)
    has_unknown_model_cost: bool = False

    def add_usage(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
        web_search_requests: int = 0,
        api_duration_ms: int = 0,
    ) -> float:
        """Record usage for an API call. Returns cost of this call in USD."""
        cost = calculate_usd_cost(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_write_tokens=cache_write_tokens,
            cache_read_tokens=cache_read_tokens,
            web_search_requests=web_search_requests,
        )

        self.total_cost_usd += cost
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_write_tokens += cache_write_tokens
        self.total_cache_read_tokens += cache_read_tokens
        self.total_web_search_requests += web_search_requests
        self.total_api_duration_ms += api_duration_ms

        # Per-model tracking
        if model not in self.model_usage:
            self.model_usage[model] = UsageRecord(model=model)
        record = self.model_usage[model]
        record.input_tokens += input_tokens
        record.output_tokens += output_tokens
        record.cache_write_tokens += cache_write_tokens
        record.cache_read_tokens += cache_read_tokens
        record.web_search_requests += web_search_requests
        record.api_duration_ms += api_duration_ms
        record.cost_usd += cost

        return cost

    def add_tool_duration(self, duration_ms: int) -> None:
        self.total_tool_duration_ms += duration_ms

    def add_lines_changed(self, added: int, removed: int) -> None:
        self.total_lines_added += added
        self.total_lines_removed += removed

    def reset(self) -> None:
        """Reset all counters."""
        self.total_cost_usd = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_write_tokens = 0
        self.total_cache_read_tokens = 0
        self.total_web_search_requests = 0
        self.total_api_duration_ms = 0
        self.total_tool_duration_ms = 0
        self.total_lines_added = 0
        self.total_lines_removed = 0
        self.model_usage = {}
        self.has_unknown_model_cost = False

    def format_cost(self) -> str:
        """Format the total cost as a string."""
        return format_cost(self.total_cost_usd)

    def format_summary(self) -> str:
        """Format a full cost summary."""
        lines = [
            f"Total cost: {self.format_cost()}",
            f"Total tokens: {self.total_input_tokens:,} input / {self.total_output_tokens:,} output",
        ]
        if self.total_cache_read_tokens > 0:
            lines.append(f"Cache: {self.total_cache_write_tokens:,} written / {self.total_cache_read_tokens:,} read")
        if len(self.model_usage) > 1:
            lines.append("By model:")
            for model, usage in self.model_usage.items():
                lines.append(f"  {model}: {format_cost(usage.cost_usd)} ({usage.input_tokens:,} in / {usage.output_tokens:,} out)")
        return "\n".join(lines)


# Module-level singleton tracker
_default_tracker = SessionCostTracker()


def get_cost_tracker() -> SessionCostTracker:
    """Get the default session cost tracker."""
    return _default_tracker


def reset_cost_tracker() -> None:
    """Reset the default session cost tracker."""
    _default_tracker.reset()


def format_cost(cost_usd: float) -> str:
    """
    Format a USD cost value for display.
    原始 TS: formatCost()
    """
    if cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.2f}"


def format_total_cost() -> str:
    """Format the total cost of the current session."""
    tracker = get_cost_tracker()
    return tracker.format_summary()
