"""Immediate command feature flag. Ported from utils/immediateCommand.ts"""

from __future__ import annotations

import os

# Cache key used by GrowthBook feature flag (Python approximation)
_FEATURE_KEY = "tengu_immediate_model_command"

# Internal cache: set once per process by _get_feature_flag
_FEATURE_CACHE: dict[str, bool] = {}


def _get_feature_flag(key: str, default: bool = False) -> bool:
    """Return a cached feature-flag value.

    In a full implementation this would query the GrowthBook SDK. Here we
    check the FEATURE_FLAGS environment variable (comma-separated list of
    enabled flags) as a lightweight substitute.
    """
    if key not in _FEATURE_CACHE:
        enabled_flags = set(
            f.strip()
            for f in os.environ.get("FEATURE_FLAGS", "").split(",")
            if f.strip()
        )
        _FEATURE_CACHE[key] = key in enabled_flags
    return _FEATURE_CACHE.get(key, default)


def should_inference_config_command_be_immediate() -> bool:
    """Return True if /model, /fast, and /effort commands should execute
    immediately during a running query rather than waiting for the turn to end.

    Always True for Anthropic employees (USER_TYPE=ant); otherwise gated by
    the ``tengu_immediate_model_command`` feature flag.
    """
    if os.environ.get("USER_TYPE") == "ant":
        return True
    return _get_feature_flag(_FEATURE_KEY, False)


def clear_feature_cache() -> None:
    """Clear the feature-flag cache (for testing)."""
    _FEATURE_CACHE.clear()
