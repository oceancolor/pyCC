"""Model configuration constants. Ported from utils/model/configs.ts"""
from __future__ import annotations
from typing import Dict, Literal

ModelKey = str
CanonicalModelId = str

# Provider → model ID mappings for each model key
ALL_MODEL_CONFIGS: Dict[ModelKey, Dict[str, str]] = {
    "sonnet4": {
        "firstParty": "claude-sonnet-4-5",
        "bedrock": "anthropic.claude-sonnet-4-5-20251120",
        "vertex": "claude-sonnet-4-5@20251120",
        "foundry": "claude-sonnet-4-5-20251120",
        "hunyuan": "claude-sonnet-4-5-20251120",
    },
    "opus45": {
        "firstParty": "claude-opus-4-5",
        "bedrock": "anthropic.claude-opus-4-5-20251101",
        "vertex": "claude-opus-4-5@20251101",
        "foundry": "claude-opus-4-5-20251101",
        "hunyuan": "claude-opus-4-5-20251101",
    },
    "haiku35": {
        "firstParty": "claude-haiku-3-5",
        "bedrock": "anthropic.claude-haiku-3-5-20241022",
        "vertex": "claude-haiku-3-5@20241022",
        "foundry": "claude-haiku-3-5-20241022",
        "hunyuan": "claude-haiku-3-5-20241022",
    },
}

CANONICAL_ID_TO_KEY: Dict[CanonicalModelId, ModelKey] = {
    v["firstParty"]: k
    for k, v in ALL_MODEL_CONFIGS.items()
}
