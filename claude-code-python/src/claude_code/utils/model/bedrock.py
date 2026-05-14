"""Bedrock-specific model utilities. Ported from utils/model/bedrock.ts"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional, List

# Cross-region inference profile prefixes for Bedrock.
BEDROCK_REGION_PREFIXES = ("us", "eu", "apac", "global")

BedrockRegionPrefix = str  # One of BEDROCK_REGION_PREFIXES


def is_foundation_model(model_id: str) -> bool:
    """Check if a model ID is a foundation model (e.g. 'anthropic.claude-sonnet-…')."""
    return model_id.startswith("anthropic.")


def extract_model_id_from_arn(model_id: str) -> str:
    """Extract the model/inference profile ID from a Bedrock ARN.

    If the input is not an ARN, returns it unchanged.

    ARN format: arn:aws:bedrock:<region>:<account>:inference-profile/<profile-id>
    Also handles: arn:aws:bedrock:<region>:<account>:application-inference-profile/<profile-id>
    And foundation model ARNs: arn:aws:bedrock:<region>::foundation-model/<model-id>
    """
    if not model_id.startswith("arn:"):
        return model_id
    last_slash = model_id.rfind("/")
    if last_slash == -1:
        return model_id
    return model_id[last_slash + 1 :]


def get_bedrock_region_prefix(model_id: str) -> Optional[BedrockRegionPrefix]:
    """Extract the region prefix from a Bedrock cross-region inference model ID.

    Handles both plain model IDs and full ARN format. For example:
    - "eu.anthropic.claude-sonnet-4-5-20250929-v1:0" → "eu"
    - "us.anthropic.claude-3-7-sonnet-20250219-v1:0" → "us"
    - "anthropic.claude-3-5-sonnet-20241022-v2:0" → None (foundation model)
    - "claude-sonnet-4-5-20250929" → None (first-party format)
    """
    effective_model_id = extract_model_id_from_arn(model_id)
    for prefix in BEDROCK_REGION_PREFIXES:
        if effective_model_id.startswith(f"{prefix}.anthropic."):
            return prefix
    return None


def apply_bedrock_region_prefix(
    model_id: str, prefix: BedrockRegionPrefix
) -> str:
    """Apply a region prefix to a Bedrock model ID.

    If the model already has a different region prefix, it will be replaced.
    If the model is a foundation model (anthropic.*), the prefix will be added.
    If the model is not a Bedrock model, it will be returned as-is.

    Examples:
    - apply_bedrock_region_prefix("us.anthropic.claude-sonnet-v1:0", "eu") → "eu.anthropic.claude-sonnet-v1:0"
    - apply_bedrock_region_prefix("anthropic.claude-sonnet-v1:0", "eu") → "eu.anthropic.claude-sonnet-v1:0"
    - apply_bedrock_region_prefix("claude-sonnet-4-5-20250929", "eu") → "claude-sonnet-4-5-20250929"
    """
    existing_prefix = get_bedrock_region_prefix(model_id)
    if existing_prefix:
        return model_id.replace(f"{existing_prefix}.", f"{prefix}.", 1)
    if is_foundation_model(model_id):
        return f"{prefix}.{model_id}"
    return model_id


def find_first_match(profiles: List[str], substring: str) -> Optional[str]:
    """Return the first profile ID that contains the given substring."""
    for p in profiles:
        if substring in p:
            return p
    return None


@lru_cache(maxsize=1)
def _get_aws_region() -> str:
    """Get the AWS region from environment variables, defaulting to us-east-1."""
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


async def get_bedrock_inference_profiles() -> List[str]:
    """List all system-defined Bedrock inference profile IDs for Anthropic models.

    Requires boto3 / botocore to be installed. Returns [] if boto3 is unavailable.
    Results are not cached at this level (callers may cache).
    """
    try:
        import boto3  # type: ignore[import]
    except ImportError:
        return []

    region = _get_aws_region()
    client = boto3.client("bedrock", region_name=region)
    all_profiles: list = []
    paginator_kwargs: dict = {"typeEquals": "SYSTEM_DEFINED"}
    next_token: Optional[str] = None

    while True:
        if next_token:
            paginator_kwargs["nextToken"] = next_token
        response = client.list_inference_profiles(**paginator_kwargs)
        summaries = response.get("inferenceProfileSummaries", [])
        all_profiles.extend(summaries)
        next_token = response.get("nextToken")
        if not next_token:
            break

    return [
        p["inferenceProfileId"]
        for p in all_profiles
        if p.get("inferenceProfileId", "").find("anthropic") >= 0
    ]


async def get_inference_profile_backing_model(profile_id: str) -> Optional[str]:
    """Get the primary backing model ID for a Bedrock inference profile.

    Returns None if boto3 is unavailable, the profile is not found, or an error occurs.
    """
    try:
        import boto3  # type: ignore[import]
    except ImportError:
        return None

    try:
        region = _get_aws_region()
        client = boto3.client("bedrock", region_name=region)
        response = client.get_inference_profile(inferenceProfileIdentifier=profile_id)
        models = response.get("models", [])
        if not models:
            return None
        primary_model = models[0]
        model_arn = primary_model.get("modelArn")
        if not model_arn:
            return None
        last_slash = model_arn.rfind("/")
        if last_slash >= 0:
            return model_arn[last_slash + 1 :]
        return model_arn
    except Exception:
        return None
