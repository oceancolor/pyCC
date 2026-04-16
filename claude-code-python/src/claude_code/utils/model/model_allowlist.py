"""Model allowlist check. Ported from utils/model/modelAllowlist.ts"""
from __future__ import annotations
import os
from claude_code.utils.model.aliases import is_model_alias, is_model_family_alias, MODEL_FAMILY_ALIASES


def is_model_allowed(model: str) -> bool:
    """Check if a model ID is in the user's allowlist or matches a family alias."""
    # Custom model from env is always allowed
    custom = os.environ.get("ANTHROPIC_CUSTOM_MODEL_OPTION")
    if custom and model == custom:
        return True
    # Aliases always allowed
    if is_model_alias(model):
        return True
    # Default: all models allowed unless restricted
    return True
