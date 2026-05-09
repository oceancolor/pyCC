"""Model string resolution utilities. Ported from utils/model/modelStrings.ts"""
from __future__ import annotations

import os
from typing import Dict, Optional

try:
    from claude_code.utils.model.configs import ALL_MODEL_CONFIGS, CANONICAL_ID_TO_KEY, ModelKey
    from claude_code.utils.model.providers import get_api_provider
except ImportError:
    ALL_MODEL_CONFIGS: Dict = {}
    CANONICAL_ID_TO_KEY: Dict = {}
    ModelKey = str  # type: ignore

    def get_api_provider():
        return "firstParty"


ModelStrings = Dict[str, str]

# Module-level cached model strings (initialized lazily)
_model_strings_state: Optional[ModelStrings] = None


def _get_builtin_model_strings(provider: str) -> ModelStrings:
    """Build a ModelStrings dict from ALL_MODEL_CONFIGS for the given provider."""
    out: ModelStrings = {}
    for key, cfg in ALL_MODEL_CONFIGS.items():
        # Fallback to firstParty if the provider key isn't present
        out[key] = cfg.get(provider, cfg.get("firstParty", ""))
    return out


def _get_initial_settings_model_overrides() -> Optional[Dict[str, str]]:
    """Read modelOverrides from settings without hard-importing the settings module."""
    try:
        from claude_code.utils.settings.settings import get_initial_settings  # type: ignore
        return get_initial_settings().get("modelOverrides")
    except Exception:
        return None


def _apply_model_overrides(ms: ModelStrings) -> ModelStrings:
    """Layer user-configured modelOverrides on top of provider-derived model strings."""
    overrides = _get_initial_settings_model_overrides()
    if not overrides:
        return ms
    out = dict(ms)
    for canonical_id, override in overrides.items():
        key = CANONICAL_ID_TO_KEY.get(canonical_id)
        if key and override:
            out[key] = override
    return out


def resolve_overridden_model(model_id: str) -> str:
    """Resolve an overridden model ID (e.g. a Bedrock ARN) back to its canonical
    first-party model ID. If the input doesn't match any current override value,
    it is returned unchanged.
    """
    overrides: Optional[Dict[str, str]] = None
    try:
        overrides = _get_initial_settings_model_overrides()
    except Exception:
        return model_id
    if not overrides:
        return model_id
    for canonical_id, override in overrides.items():
        if override == model_id:
            return canonical_id
    return model_id


def _init_model_strings() -> None:
    global _model_strings_state
    if _model_strings_state is not None:
        return
    provider = get_api_provider()
    # For non-Bedrock providers, initialize synchronously
    if provider != "bedrock":
        _model_strings_state = _get_builtin_model_strings(provider)
    # For Bedrock, fall through; get_model_strings will use interim defaults


def get_model_strings() -> ModelStrings:
    """Return the current ModelStrings mapping (provider-aware)."""
    global _model_strings_state
    if _model_strings_state is None:
        _init_model_strings()
        # May still be None on Bedrock while async fetch runs; use interim defaults
        return _apply_model_overrides(_get_builtin_model_strings(get_api_provider()))
    return _apply_model_overrides(_model_strings_state)


def set_model_strings(ms: ModelStrings) -> None:
    """Set the model strings state (used by bootstrap/state)."""
    global _model_strings_state
    _model_strings_state = ms


async def ensure_model_strings_initialized() -> None:
    """Ensure model strings are fully initialized (waits for Bedrock if needed)."""
    global _model_strings_state
    if _model_strings_state is not None:
        return
    provider = get_api_provider()
    if provider != "bedrock":
        _model_strings_state = _get_builtin_model_strings(provider)
        return
    # Bedrock: try to fetch inference profiles
    try:
        from claude_code.utils.model.bedrock import get_bedrock_inference_profiles, find_first_match  # type: ignore
        profiles = await get_bedrock_inference_profiles()
        if profiles:
            fallback = _get_builtin_model_strings("bedrock")
            out: ModelStrings = {}
            for key, cfg in ALL_MODEL_CONFIGS.items():
                needle = cfg.get("firstParty", "")
                matched = find_first_match(profiles, needle)
                out[key] = matched if matched else fallback.get(key, "")
            _model_strings_state = out
            return
    except Exception:
        pass
    _model_strings_state = _get_builtin_model_strings("bedrock")
