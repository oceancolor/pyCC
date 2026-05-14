"""Agent model utilities. Ported from utils/model/agent.ts"""

from __future__ import annotations

import os
from typing import Optional, List

from .aliases import MODEL_ALIASES

# All valid agent model options: all aliases + 'inherit'
AGENT_MODEL_OPTIONS: tuple = tuple(list(MODEL_ALIASES) + ["inherit"])

AgentModelAlias = str  # One of AGENT_MODEL_OPTIONS


class AgentModelOption:
    """Descriptor for an agent model choice."""

    def __init__(self, value: str, label: str, description: str) -> None:
        self.value = value
        self.label = label
        self.description = description

    def to_dict(self) -> dict:
        return {"value": self.value, "label": self.label, "description": self.description}


def get_default_subagent_model() -> str:
    """Get the default subagent model (inherit from parent)."""
    return "inherit"


def _alias_matches_parent_tier(alias: str, parent_model: str) -> bool:
    """Check if a bare family alias (opus/sonnet/haiku) matches the parent model tier.

    When it does, the subagent inherits the parent's exact model string
    instead of resolving the alias to a provider default.
    """
    from .model import get_canonical_name

    canonical = get_canonical_name(parent_model)
    alias_lower = alias.lower()
    if alias_lower == "opus":
        return "opus" in canonical
    if alias_lower == "sonnet":
        return "sonnet" in canonical
    if alias_lower == "haiku":
        return "haiku" in canonical
    return False


def get_agent_model(
    agent_model: Optional[str],
    parent_model: str,
    tool_specified_model: Optional[str] = None,
    permission_mode: Optional[str] = None,
) -> str:
    """Get the effective model string for an agent.

    For Bedrock, if the parent model uses a cross-region inference prefix
    (e.g., 'eu.', 'us.'), that prefix is inherited by subagents using alias
    models. This ensures subagents use the same region as the parent.
    """
    from .bedrock import get_bedrock_region_prefix, apply_bedrock_region_prefix
    from .model import parse_user_specified_model, get_runtime_main_loop_model
    from .providers import get_api_provider

    env_model = os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL")
    if env_model:
        return parse_user_specified_model(env_model)

    parent_region_prefix = get_bedrock_region_prefix(parent_model)

    def apply_parent_region_prefix(resolved_model: str, original_spec: str) -> str:
        if parent_region_prefix and get_api_provider() == "bedrock":
            if get_bedrock_region_prefix(original_spec):
                return resolved_model
            return apply_bedrock_region_prefix(resolved_model, parent_region_prefix)
        return resolved_model

    if tool_specified_model:
        if _alias_matches_parent_tier(tool_specified_model, parent_model):
            return parent_model
        model = parse_user_specified_model(tool_specified_model)
        return apply_parent_region_prefix(model, tool_specified_model)

    agent_model_with_exp = agent_model if agent_model is not None else get_default_subagent_model()

    if agent_model_with_exp == "inherit":
        return get_runtime_main_loop_model(
            permission_mode=permission_mode or "default",
            main_loop_model=parent_model,
            exceeds_200k_tokens=False,
        )

    if _alias_matches_parent_tier(agent_model_with_exp, parent_model):
        return parent_model

    model = parse_user_specified_model(agent_model_with_exp)
    return apply_parent_region_prefix(model, agent_model_with_exp)


def get_agent_model_display(model: Optional[str]) -> str:
    """Get a human-readable display string for an agent model setting."""
    if not model:
        return "Inherit from parent (default)"
    if model == "inherit":
        return "Inherit from parent"
    return model.capitalize()


def get_agent_model_options() -> List[AgentModelOption]:
    """Get available model options for agents."""
    return [
        AgentModelOption(
            value="sonnet",
            label="Sonnet",
            description="Balanced performance - best for most agents",
        ),
        AgentModelOption(
            value="opus",
            label="Opus",
            description="Most capable for complex reasoning tasks",
        ),
        AgentModelOption(
            value="haiku",
            label="Haiku",
            description="Fast and efficient for simple tasks",
        ),
        AgentModelOption(
            value="inherit",
            label="Inherit from parent",
            description="Use the same model as the main conversation",
        ),
    ]
