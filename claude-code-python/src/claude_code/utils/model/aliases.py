"""Model alias constants. Ported from utils/model/aliases.ts"""
from __future__ import annotations
from typing import Tuple

MODEL_ALIASES: Tuple[str, ...] = (
    "sonnet", "opus", "haiku", "best", "sonnet[1m]", "opus[1m]", "opusplan"
)
ModelAlias = str
MODEL_FAMILY_ALIASES = ("sonnet", "opus", "haiku")


def is_model_alias(model: str) -> bool:
    return model in MODEL_ALIASES


def is_model_family_alias(model: str) -> bool:
    return model in MODEL_FAMILY_ALIASES
