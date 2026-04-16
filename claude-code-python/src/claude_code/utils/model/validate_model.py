"""Model validation. Ported from utils/model/validateModel.ts"""
from __future__ import annotations
import os
from typing import TypedDict
from claude_code.utils.model.aliases import is_model_alias
from claude_code.utils.model.model_allowlist import is_model_allowed

_cache: dict = {}


class ValidationResult(TypedDict, total=False):
    valid: bool
    error: str


async def validate_model(model: str) -> ValidationResult:
    normalized = model.strip()
    if not normalized:
        return {"valid": False, "error": "Model name cannot be empty"}
    if not is_model_allowed(normalized):
        return {"valid": False, "error": f"Model '{normalized}' is not in the list of available models"}
    if is_model_alias(normalized):
        return {"valid": True}
    if normalized == os.environ.get("ANTHROPIC_CUSTOM_MODEL_OPTION", ""):
        return {"valid": True}
    if normalized in _cache:
        return {"valid": True}
    # Optimistic: assume valid (no live API call without credentials)
    return {"valid": True}
