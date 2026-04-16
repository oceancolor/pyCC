"""
Model utilities
原始 TS: src/utils/model/model.ts (partial port)
"""
from __future__ import annotations

import os
from typing import Optional

# Default model constants
DEFAULT_SONNET_MODEL = "claude-sonnet-4-5"
DEFAULT_HAIKU_MODEL = "claude-3-5-haiku-20241022"
DEFAULT_OPUS_MODEL = "claude-opus-4-5"


def get_default_sonnet_model() -> str:
    return DEFAULT_SONNET_MODEL


def get_default_haiku_model() -> str:
    return DEFAULT_HAIKU_MODEL


def get_small_fast_model() -> str:
    """Get the small/fast model (used for quick tasks)."""
    return os.environ.get("ANTHROPIC_SMALL_FAST_MODEL") or DEFAULT_HAIKU_MODEL


def get_main_loop_model() -> str:
    """
    Get the main model to use for the conversation loop.
    Priority: ANTHROPIC_MODEL env → default Sonnet
    """
    return os.environ.get("ANTHROPIC_MODEL") or DEFAULT_SONNET_MODEL


def normalize_model_string_for_api(model: str) -> str:
    """Normalize a model alias/name to the API string."""
    # TODO: port aliases.ts resolution
    return model
