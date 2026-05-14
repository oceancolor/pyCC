"""Model capability support overrides for 3P providers. Ported from utils/model/modelSupportOverrides.ts"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional, Literal

ModelCapabilityOverride = Literal[
    "effort", "max_effort", "thinking", "adaptive_thinking", "interleaved_thinking"
]

_TIERS = [
    {
        "model_env_var": "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "capabilities_env_var": "ANTHROPIC_DEFAULT_OPUS_MODEL_SUPPORTED_CAPABILITIES",
    },
    {
        "model_env_var": "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "capabilities_env_var": "ANTHROPIC_DEFAULT_SONNET_MODEL_SUPPORTED_CAPABILITIES",
    },
    {
        "model_env_var": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "capabilities_env_var": "ANTHROPIC_DEFAULT_HAIKU_MODEL_SUPPORTED_CAPABILITIES",
    },
]


@lru_cache(maxsize=128)
def get_3p_model_capability_override(
    model: str, capability: ModelCapabilityOverride
) -> Optional[bool]:
    """Check whether a 3P model capability override is set for a model.

    This matches against pinned ANTHROPIC_DEFAULT_*_MODEL env vars and reads
    the corresponding ANTHROPIC_DEFAULT_*_MODEL_SUPPORTED_CAPABILITIES env var.

    Returns:
        True/False if an explicit override exists, None if not applicable
        (first-party provider or no env vars set).
    """
    from .providers import get_api_provider

    if get_api_provider() == "firstParty":
        return None

    model_lower = model.lower()
    for tier in _TIERS:
        pinned = os.environ.get(tier["model_env_var"])
        capabilities = os.environ.get(tier["capabilities_env_var"])
        if not pinned or capabilities is None:
            continue
        if model_lower != pinned.lower():
            continue
        caps = [c.strip().lower() for c in capabilities.split(",")]
        return capability.lower() in caps

    return None
