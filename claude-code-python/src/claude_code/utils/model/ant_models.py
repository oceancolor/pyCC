"""Ant (internal Anthropic) model override utilities. Ported from utils/model/antModels.ts"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class AntModel:
    """An internal Anthropic model definition."""

    alias: str
    model: str
    label: str
    description: Optional[str] = None
    default_effort_value: Optional[float] = None
    default_effort_level: Optional[str] = None
    context_window: Optional[int] = None
    default_max_tokens: Optional[int] = None
    upper_max_tokens_limit: Optional[int] = None
    # Model defaults to adaptive thinking and rejects thinking: { type: 'disabled' }
    always_on_thinking: bool = False


@dataclass
class AntModelSwitchCalloutConfig:
    """Configuration for a model-switch callout."""

    description: str
    version: str
    model_alias: Optional[str] = None


@dataclass
class AntModelOverrideConfig:
    """Full override config returned by the GrowthBook feature flag."""

    default_model: Optional[str] = None
    default_model_effort_level: Optional[str] = None
    default_system_prompt_suffix: Optional[str] = None
    ant_models: List[AntModel] = field(default_factory=list)
    switch_callout: Optional[AntModelSwitchCalloutConfig] = None


def get_ant_model_override_config() -> Optional[AntModelOverrideConfig]:
    """Return the ant-model override config from GrowthBook, or None for non-ant users.

    In the Python port we don't have a live GrowthBook client, so we return None
    unless the USER_TYPE env var is set to 'ant'. The real implementation would
    call getFeatureValue_CACHED_MAY_BE_STALE('tengu_ant_model_override', null).
    """
    if os.environ.get("USER_TYPE") != "ant":
        return None
    # In production this would read from GrowthBook.
    # For the Python port, honour an env var for testing purposes.
    return None


def get_ant_models() -> List[AntModel]:
    """Return the list of ant-only models, or [] for non-ant users."""
    if os.environ.get("USER_TYPE") != "ant":
        return []
    config = get_ant_model_override_config()
    if config is None:
        return []
    return config.ant_models


def resolve_ant_model(model: Optional[str]) -> Optional[AntModel]:
    """Resolve a model string to an AntModel entry, or None if not found/applicable."""
    if os.environ.get("USER_TYPE") != "ant":
        return None
    if model is None:
        return None
    lower = model.lower()
    for m in get_ant_models():
        if m.alias == model or lower in m.model.lower():
            return m
    return None
