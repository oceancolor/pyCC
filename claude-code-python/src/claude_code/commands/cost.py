"""
/cost command — Display token usage and estimated cost for this session
原始 TS: src/commands/cost/

Usage: /cost
Shows input/output token counts and USD cost estimate.
"""
from __future__ import annotations

from typing import Any, Optional


# Pricing as of early 2025 (USD per million tokens)
# Source: https://www.anthropic.com/pricing
_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-5": {"input": 15.0, "output": 75.0},
    "claude-opus-4": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20240620": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}

_DEFAULT_PRICING = {"input": 3.0, "output": 15.0}  # fallback: sonnet pricing


def _get_pricing(model: str) -> dict[str, float]:
    """Return per-million-token pricing for a model (with prefix matching)."""
    # Exact match first
    if model in _PRICING:
        return _PRICING[model]
    # Prefix match (e.g. "claude-opus-4-5-20250514" → "claude-opus-4-5")
    for key in _PRICING:
        if model.startswith(key):
            return _PRICING[key]
    return _DEFAULT_PRICING


def _calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate USD cost from token counts."""
    pricing = _get_pricing(model)
    cost = (input_tokens / 1_000_000) * pricing["input"]
    cost += (output_tokens / 1_000_000) * pricing["output"]
    return cost


def cost_command(session: Any) -> str:
    """
    Display token usage and estimated cost for the current session.

    Args:
        session: The current session object. Expected to have:
            - usage: dict or object with input_tokens / output_tokens
            - model: str model name (optional)
            - turn_count: int number of turns (optional)

    Returns:
        Formatted usage and cost report string.
    """
    # Extract usage data
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0

    usage = getattr(session, "usage", None)

    if usage is None:
        return "No usage data available for this session."

    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read_tokens = usage.get("cache_read_input_tokens", 0)
        cache_write_tokens = usage.get("cache_creation_input_tokens", 0)
    else:
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0)
        cache_write_tokens = getattr(usage, "cache_creation_input_tokens", 0)

    model = getattr(session, "model", "unknown")
    turn_count = getattr(session, "turn_count", None)

    total_tokens = input_tokens + output_tokens
    cost_usd = _calculate_cost(input_tokens, output_tokens, model or "")

    lines = [
        "─" * 40,
        "  Session Cost & Usage",
        "─" * 40,
    ]

    if model and model != "unknown":
        lines.append(f"  Model:          {model}")

    if turn_count is not None:
        lines.append(f"  Turns:          {turn_count}")

    lines.append("")
    lines.append(f"  Input tokens:   {input_tokens:,}")
    lines.append(f"  Output tokens:  {output_tokens:,}")

    if cache_read_tokens:
        lines.append(f"  Cache read:     {cache_read_tokens:,}")
    if cache_write_tokens:
        lines.append(f"  Cache write:    {cache_write_tokens:,}")

    lines.append(f"  Total tokens:   {total_tokens:,}")
    lines.append("")
    lines.append(f"  Est. cost:      ${cost_usd:.4f} USD")
    lines.append("─" * 40)

    pricing = _get_pricing(model or "")
    lines.append(
        f"  (@ ${pricing['input']}/M input, ${pricing['output']}/M output)"
    )

    return "\n".join(lines)
