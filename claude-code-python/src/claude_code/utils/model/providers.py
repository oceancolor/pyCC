"""API provider detection. Ported from utils/model/providers.ts"""
from __future__ import annotations
import os
from typing import Literal
from urllib.parse import urlparse

APIProvider = Literal["firstParty", "bedrock", "vertex", "foundry", "hunyuan"]


def get_api_provider() -> APIProvider:
    if os.environ.get("HUNYUAN_API_KEY"):
        return "hunyuan"
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK", "").lower() in ("1", "true"):
        return "bedrock"
    if os.environ.get("CLAUDE_CODE_USE_VERTEX", "").lower() in ("1", "true"):
        return "vertex"
    if os.environ.get("CLAUDE_CODE_USE_FOUNDRY", "").lower() in ("1", "true"):
        return "foundry"
    return "firstParty"


def is_first_party_anthropic_base_url() -> bool:
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if not base_url:
        return True
    try:
        host = urlparse(base_url).hostname or ""
        allowed = {"api.anthropic.com"}
        if os.environ.get("USER_TYPE") == "ant":
            allowed.add("api-staging.anthropic.com")
        return host in allowed
    except Exception:
        return False
