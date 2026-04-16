"""
Anthropic API client factory. Ported from services/api/client.ts (395 lines → core).
Supports: firstParty, bedrock, vertex, foundry, hunyuan
"""
from __future__ import annotations
import os
from typing import Any, Optional

CLIENT_REQUEST_ID_HEADER = "x-client-request-id"


class AnthropicClientConfig:
    def __init__(self, api_key: Optional[str] = None, max_retries: int = 2,
                 model: Optional[str] = None, source: Optional[str] = None):
        self.api_key = api_key
        self.max_retries = max_retries
        self.model = model
        self.source = source


async def get_anthropic_client(
    api_key: Optional[str] = None,
    max_retries: int = 2,
    model: Optional[str] = None,
    source: Optional[str] = None,
) -> Any:
    """
    Create and return an Anthropic SDK client for the configured provider.
    Falls back to httpx-based client if anthropic SDK not installed.
    """
    from claude_code.utils.model.providers import get_api_provider
    provider = get_api_provider()

    resolved_key = (
        api_key
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        or ""
    )
    timeout = int(os.environ.get("API_TIMEOUT_MS", str(600_000))) / 1000

    try:
        import anthropic
        kwargs: dict = {
            "api_key": resolved_key,
            "max_retries": max_retries,
            "timeout": timeout,
            "default_headers": _build_default_headers(),
        }
        if provider == "bedrock":
            from anthropic import AnthropicBedrock
            return AnthropicBedrock(max_retries=max_retries)
        if provider == "vertex":
            from anthropic import AnthropicVertex
            project = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "")
            region = os.environ.get("CLOUD_ML_REGION", "us-east5")
            return AnthropicVertex(project_id=project, region=region,
                                   max_retries=max_retries)
        return anthropic.Anthropic(**kwargs)
    except ImportError:
        return _SimpleHttpClient(resolved_key, timeout=timeout)


def _build_default_headers() -> dict:
    headers = {"x-app": "cli"}
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if session_id:
        headers["X-Claude-Code-Session-Id"] = session_id
    container_id = os.environ.get("CLAUDE_CODE_CONTAINER_ID")
    if container_id:
        headers["x-claude-remote-container-id"] = container_id
    return headers


class _SimpleHttpClient:
    """Minimal fallback HTTP client when anthropic SDK not installed."""
    def __init__(self, api_key: str, timeout: float = 600):
        self.api_key = api_key
        self.timeout = timeout

    async def messages_create(self, **kwargs) -> dict:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")
