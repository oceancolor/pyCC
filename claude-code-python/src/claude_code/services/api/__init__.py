"""
Anthropic API client factory
原始 TS: src/services/api/client.ts

anthropic-ai/sdk → anthropic Python SDK
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import anthropic

from claude_code.utils.env_utils import is_env_truthy, get_aws_region, get_vertex_region_for_model


def get_anthropic_api_key() -> Optional[str]:
    """Get the Anthropic API key from environment."""
    return os.environ.get("ANTHROPIC_API_KEY")


def get_api_provider() -> str:
    """
    Determine the API provider from environment.
    原始 TS: getAPIProvider
    """
    if os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") or os.environ.get("AWS_BEDROCK_RUNTIME_ENDPOINT"):
        return "bedrock"
    if os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID"):
        return "vertex"
    if os.environ.get("ANTHROPIC_FOUNDRY_RESOURCE") or os.environ.get("ANTHROPIC_FOUNDRY_BASE_URL"):
        return "foundry"
    return "anthropic"


def get_anthropic_client(
    model: Optional[str] = None,
    *,
    timeout: float = 600.0,
) -> anthropic.Anthropic:
    """
    Create and return an Anthropic API client.
    原始 TS: getAnthropicClient
    """
    provider = get_api_provider()
    api_key = get_anthropic_api_key()

    if provider == "bedrock":
        # TODO: Port Bedrock client (requires boto3)
        # TODO: bedrock support
        raise NotImplementedError("Bedrock provider not yet implemented in Python port")

    if provider == "vertex":
        # TODO: Port Vertex AI client (requires google-auth-library)
        raise NotImplementedError("Vertex AI provider not yet implemented in Python port")

    if provider == "foundry":
        # TODO: Port Azure Foundry client
        raise NotImplementedError("Azure Foundry provider not yet implemented in Python port")

    # Direct Anthropic API
    if not api_key:
        raise ValueError(
            "No API key found. Please set the ANTHROPIC_API_KEY environment variable."
        )

    base_url = os.environ.get("ANTHROPIC_BASE_URL")

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    return client
