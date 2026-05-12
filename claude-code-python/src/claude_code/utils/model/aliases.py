"""
Model alias constants and helpers.
Ported from utils/model/aliases.ts
"""
from __future__ import annotations

from typing import List

MODEL_ALIASES: List[str] = [
    "sonnet",
    "opus",
    "haiku",
    "best",
    "sonnet[1m]",
    "opus[1m]",
    "opusplan",
]

# Family aliases that act as wildcards in the availableModels allowlist
MODEL_FAMILY_ALIASES: List[str] = ["sonnet", "opus", "haiku"]


def is_model_alias(model_input: str) -> bool:
    """Return True if *model_input* is a known model alias."""
    return model_input in MODEL_ALIASES


def is_model_family_alias(model: str) -> bool:
    """Return True if *model* is a bare family alias (sonnet/opus/haiku).

    When a family alias is in the allowlist, ANY model in that family is allowed.
    """
    return model in MODEL_FAMILY_ALIASES
