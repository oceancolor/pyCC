"""Model deprecation utilities. Ported from utils/model/deprecation.ts"""

from __future__ import annotations

from typing import Optional, Dict

from .providers import get_api_provider

# Deprecated models and their retirement dates by provider.
# Keys are substrings to match in model IDs (case-insensitive).
_DEPRECATED_MODELS: Dict[str, Dict] = {
    "claude-3-opus": {
        "model_name": "Claude 3 Opus",
        "retirement_dates": {
            "firstParty": "January 5, 2026",
            "bedrock": "January 15, 2026",
            "vertex": "January 5, 2026",
            "foundry": "January 5, 2026",
        },
    },
    "claude-3-7-sonnet": {
        "model_name": "Claude 3.7 Sonnet",
        "retirement_dates": {
            "firstParty": "February 19, 2026",
            "bedrock": "April 28, 2026",
            "vertex": "May 11, 2026",
            "foundry": "February 19, 2026",
        },
    },
    "claude-3-5-haiku": {
        "model_name": "Claude 3.5 Haiku",
        "retirement_dates": {
            "firstParty": "February 19, 2026",
            "bedrock": None,
            "vertex": None,
            "foundry": None,
        },
    },
}


def _get_deprecated_model_info(model_id: str) -> Optional[dict]:
    """Check if a model is deprecated. Returns None if not deprecated.

    Returns a dict with keys: model_name, retirement_date.
    """
    lower_model_id = model_id.lower()
    provider = get_api_provider()

    for key, value in _DEPRECATED_MODELS.items():
        retirement_date = value["retirement_dates"].get(provider)
        if key not in lower_model_id or not retirement_date:
            continue
        return {
            "model_name": value["model_name"],
            "retirement_date": retirement_date,
        }
    return None


def get_model_deprecation_warning(model_id: Optional[str]) -> Optional[str]:
    """Get a deprecation warning message for a model, or None if not deprecated.

    Args:
        model_id: The model ID to check. Returns None if falsy.

    Returns:
        A warning string like "⚠ Claude 3 Opus will be retired on January 5, 2026. …"
        or None if the model is not deprecated (or model_id is falsy).
    """
    if not model_id:
        return None

    info = _get_deprecated_model_info(model_id)
    if not info:
        return None

    return (
        f"⚠ {info['model_name']} will be retired on {info['retirement_date']}. "
        "Consider switching to a newer model."
    )
