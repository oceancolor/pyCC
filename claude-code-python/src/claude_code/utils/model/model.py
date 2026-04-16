"""Model selection utilities. Ported from utils/model/model.ts"""
from __future__ import annotations
import os
from typing import Optional
from claude_code.utils.model.aliases import is_model_alias, ModelAlias
from claude_code.utils.model.providers import get_api_provider

ModelName = str
ModelSetting = Optional[str]

DEFAULT_SONNET_MODEL = "claude-sonnet-4-5"
DEFAULT_OPUS_MODEL = "claude-opus-4-5"
DEFAULT_HAIKU_MODEL = "claude-haiku-3-5"


def get_default_haiku_model() -> ModelName:
    return os.environ.get("ANTHROPIC_SMALL_FAST_MODEL") or DEFAULT_HAIKU_MODEL


def get_small_fast_model() -> ModelName:
    if os.environ.get("HUNYUAN_API_KEY"):
        return os.environ.get("ANTHROPIC_SMALL_FAST_MODEL", "hunyuan-lite")
    return os.environ.get("ANTHROPIC_SMALL_FAST_MODEL") or get_default_haiku_model()


def get_default_sonnet_model() -> ModelName:
    return os.environ.get("ANTHROPIC_SONNET_MODEL") or DEFAULT_SONNET_MODEL


def get_default_opus_model() -> ModelName:
    return os.environ.get("ANTHROPIC_OPUS_MODEL") or DEFAULT_OPUS_MODEL


def get_best_model() -> ModelName:
    return get_default_opus_model()


def get_default_main_loop_model() -> ModelName:
    return get_default_sonnet_model()


def get_default_main_loop_model_setting() -> ModelName:
    return get_default_sonnet_model()


def normalize_model_string_for_api(model: str) -> ModelName:
    """Expand alias to a concrete model ID."""
    m = model.strip().lower()
    alias_map = {
        "sonnet": get_default_sonnet_model(),
        "opus": get_default_opus_model(),
        "haiku": get_default_haiku_model(),
        "best": get_best_model(),
    }
    return alias_map.get(m, model)


def parse_user_specified_model(model: str) -> ModelName:
    return normalize_model_string_for_api(model)


def get_main_loop_model() -> ModelName:
    return get_default_main_loop_model()
