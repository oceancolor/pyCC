"""
Teammate model fallback.
原始 TS: utils/swarm/teammateModel.ts
"""

import os
from typing import Dict

# Fallback model configs for teammates (opus-4-6 when available, else opus-4-5)
_TEAMMATE_MODEL_CONFIGS: Dict[str, str] = {
    "firstParty": "claude-opus-4-6",
    "bedrock": "anthropic.claude-opus-4-6-20260501",
    "vertex": "claude-opus-4-6@20260501",
    "foundry": "claude-opus-4-6-20260501",
    "hunyuan": "claude-opus-4-6-20260501",
}


def get_hardcoded_teammate_model_fallback() -> str:
    """Return the default model for new teammates.

    When the user has never set teammateDefaultModel in /config, new teammates
    use Opus 4.6. Must be provider-aware so Bedrock/Vertex/Foundry customers
    get the correct model ID.
    """
    try:
        from ..model.providers import get_api_provider
        provider = get_api_provider()
        return _TEAMMATE_MODEL_CONFIGS.get(provider, _TEAMMATE_MODEL_CONFIGS["firstParty"])
    except Exception:
        return _TEAMMATE_MODEL_CONFIGS["firstParty"]
