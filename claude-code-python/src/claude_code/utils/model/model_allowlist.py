"""
Model allowlist guard.
Ported from utils/model/modelAllowlist.ts

Checks whether a user-specified model is permitted by the enterprise
availableModels allowlist.
"""
from __future__ import annotations

import re
from typing import List, Optional


def _is_model_alias(model: str) -> bool:
    try:
        from claude_code.utils.model.aliases import is_model_alias
        return is_model_alias(model)
    except ImportError:
        return False


def _is_model_family_alias(model: str) -> bool:
    try:
        from claude_code.utils.model.aliases import is_model_family_alias
        return is_model_family_alias(model)
    except ImportError:
        return model in ("sonnet", "opus", "haiku")


def _parse_user_specified_model(model: str) -> str:
    try:
        from claude_code.utils.model.model import parse_user_specified_model
        return parse_user_specified_model(model)
    except ImportError:
        return model


def _resolve_overridden_model(model: str) -> str:
    try:
        from claude_code.utils.model.model import resolve_overridden_model
        return resolve_overridden_model(model)
    except ImportError:
        return model


def _get_available_models_from_settings() -> Optional[List[str]]:
    try:
        from claude_code.utils.settings.settings import get_settings_deprecated
        settings = get_settings_deprecated() or {}
        return settings.get("availableModels")
    except ImportError:
        return None


def _model_matches_version_prefix(model: str, prefix: str) -> bool:
    """Return True if *model* starts with *prefix* at a segment boundary.

    e.g. "claude-opus-4-5-20251101" matches prefix "claude-opus-4-5".
    """
    if not model.startswith(prefix):
        return False
    remaining = model[len(prefix):]
    return not remaining or remaining.startswith("-")


def _family_has_specific_entries(family: str, allowlist: List[str]) -> bool:
    """Return True if *allowlist* contains any entry that is a specific version of *family*."""
    for entry in allowlist:
        if _is_model_family_alias(entry):
            continue
        if family in entry:
            return True
    return False


def _model_belongs_to_family(model: str, family: str) -> bool:
    """Return True if *model* belongs to the family denoted by *family*."""
    return family in model


def is_model_allowed(model: str) -> bool:
    """Return True if *model* is permitted by the enterprise allowlist.

    If ``availableModels`` is not set in settings, all models are allowed.

    Matching tiers:
    1. Family aliases ("opus", "sonnet", "haiku") — wildcard for the entire
       family, UNLESS more specific entries exist (e.g. "opus-4-5").
    2. Version prefixes ("opus-4-5", "claude-opus-4-5") — any build of that
       version.
    3. Full model IDs ("claude-opus-4-5-20251101") — exact match only.
    """
    available_models = _get_available_models_from_settings()
    if available_models is None:
        return True
    if len(available_models) == 0:
        return False

    resolved = _resolve_overridden_model(model)
    normalized = resolved.strip().lower()
    normalized_allowlist = [m.strip().lower() for m in available_models]

    # Direct match
    if normalized in normalized_allowlist:
        if (
            not _is_model_family_alias(normalized)
            or not _family_has_specific_entries(normalized, normalized_allowlist)
        ):
            return True

    # Family aliases in allowlist
    for entry in normalized_allowlist:
        if (
            _is_model_family_alias(entry)
            and not _family_has_specific_entries(entry, normalized_allowlist)
            and _model_belongs_to_family(normalized, entry)
        ):
            return True

    # Alias → resolved model check
    if _is_model_alias(normalized):
        resolved_alias = _parse_user_specified_model(normalized).lower()
        if resolved_alias in normalized_allowlist:
            return True

    # Allowlist alias → model check
    for entry in normalized_allowlist:
        if not _is_model_family_alias(entry) and _is_model_alias(entry):
            resolved_entry = _parse_user_specified_model(entry).lower()
            if resolved_entry == normalized:
                return True

    # Version-prefix matching
    for entry in normalized_allowlist:
        if not _is_model_family_alias(entry) and not _is_model_alias(entry):
            if _model_matches_version_prefix(normalized, entry):
                return True

    return False
