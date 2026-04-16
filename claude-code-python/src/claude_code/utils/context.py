"""
Python port of: src/utils/context.ts
Provides context window sizing, output token limits, and usage percentage
calculations for various Claude models.

Note: Growthbook/analytics calls are stubbed out (return False/None).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_CONTEXT_WINDOW_DEFAULT: int = 200_000
COMPACT_MAX_OUTPUT_TOKENS: int = 20_000
MAX_OUTPUT_TOKENS_DEFAULT: int = 32_000
MAX_OUTPUT_TOKENS_UPPER_LIMIT: int = 64_000
CAPPED_DEFAULT_MAX_TOKENS: int = 8_000
ESCALATED_MAX_TOKENS: int = 64_000


# ---------------------------------------------------------------------------
# 1M context helpers
# ---------------------------------------------------------------------------

def is_1m_context_disabled() -> bool:
    """Return True if 1M context is disabled via env var."""
    val = os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "").strip().lower()
    return val in ("1", "true", "yes")


def has_1m_context(model: str) -> bool:
    """Return True if the model name contains '[1m]' (case-insensitive)."""
    return "[1m]" in model.lower()


def model_supports_1m(model: str) -> bool:
    """
    Return True if the canonical model name supports 1M context.
    Checks for 'sonnet-4' or 'opus-4-6' in the model string (case-insensitive).
    """
    lower = model.lower()
    return "sonnet-4" in lower or "opus-4-6" in lower


# ---------------------------------------------------------------------------
# Context window
# ---------------------------------------------------------------------------

def get_context_window_for_model(
    model: str,
    betas: Optional[List[str]] = None,
) -> int:
    """
    Return the context window size (in tokens) for the given model.

    Priority order:
      1. CLAUDE_CODE_MAX_CONTEXT_TOKENS env override
      2. 1M context (if model supports it and not disabled)
      3. DEFAULT (200_000)
    """
    if betas is None:
        betas = []

    # Env override
    env_val = os.environ.get("CLAUDE_CODE_MAX_CONTEXT_TOKENS", "").strip()
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass

    # 1M context path
    if not is_1m_context_disabled():
        if has_1m_context(model) or model_supports_1m(model):
            return 1_000_000

    return MODEL_CONTEXT_WINDOW_DEFAULT


# ---------------------------------------------------------------------------
# Context usage percentages
# ---------------------------------------------------------------------------

def calculate_context_percentages(
    current_usage: Optional[Dict],
    context_window_size: int,
) -> Dict[str, float]:
    """
    Calculate used/remaining context as percentages.

    Args:
        current_usage: Dict with at least an 'input_tokens' key, or None.
        context_window_size: Total context window in tokens.

    Returns:
        Dict with keys 'used' and 'remaining' (both as floats 0–100).
    """
    if not current_usage or context_window_size <= 0:
        return {"used": 0.0, "remaining": 100.0}

    input_tokens: int = current_usage.get("input_tokens", 0) or 0
    cache_creation: int = current_usage.get("cache_creation_input_tokens", 0) or 0
    cache_read: int = current_usage.get("cache_read_input_tokens", 0) or 0

    total_used = input_tokens + cache_creation + cache_read
    used_pct = min(100.0, (total_used / context_window_size) * 100.0)
    remaining_pct = max(0.0, 100.0 - used_pct)

    return {"used": used_pct, "remaining": remaining_pct}


# ---------------------------------------------------------------------------
# Max output tokens
# ---------------------------------------------------------------------------

def get_model_max_output_tokens(model: str) -> Dict[str, int]:
    """
    Return the default and upper-limit max output tokens for the given model.

    Returns:
        Dict with keys 'default' and 'upper_limit'.
    """
    lower = model.lower()

    # claude-3-5-haiku and claude-3-haiku — smaller output window
    if "haiku" in lower:
        return {
            "default": CAPPED_DEFAULT_MAX_TOKENS,
            "upper_limit": MAX_OUTPUT_TOKENS_DEFAULT,
        }

    # claude-3-opus and earlier — standard limits
    if "opus-3" in lower or "claude-3-opus" in lower:
        return {
            "default": MAX_OUTPUT_TOKENS_DEFAULT,
            "upper_limit": MAX_OUTPUT_TOKENS_UPPER_LIMIT,
        }

    # claude-3-5-sonnet and newer / claude-3-7 / claude-4 series
    # All get the escalated upper limit
    if (
        "sonnet" in lower
        or "opus-4" in lower
        or "claude-4" in lower
        or "claude-3-7" in lower
    ):
        return {
            "default": MAX_OUTPUT_TOKENS_DEFAULT,
            "upper_limit": ESCALATED_MAX_TOKENS,
        }

    # Default fallback
    return {
        "default": MAX_OUTPUT_TOKENS_DEFAULT,
        "upper_limit": MAX_OUTPUT_TOKENS_UPPER_LIMIT,
    }


# ---------------------------------------------------------------------------
# Max thinking tokens
# ---------------------------------------------------------------------------

def get_max_thinking_tokens_for_model(model: str) -> int:
    """
    Return the maximum thinking tokens for the given model.
    Equals upper_limit - 1 so there is always room for at least one output token.
    """
    limits = get_model_max_output_tokens(model)
    return limits["upper_limit"] - 1
