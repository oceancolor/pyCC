"""
Teleport environment management.
Ported from utils/teleport/environments.ts
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

log = logging.getLogger(__name__)


class EnvironmentResource(TypedDict):
    kind: str  # 'anthropic_cloud' | 'byoc' | 'bridge'
    environment_id: str
    name: str
    created_at: str
    state: str  # 'active'


class EnvironmentListResponse(TypedDict, total=False):
    environments: List[EnvironmentResource]
    has_more: bool
    first_id: Optional[str]
    last_id: Optional[str]


def _get_claude_ai_oauth_tokens() -> Optional[Dict[str, Any]]:
    try:
        from claude_code.utils.auth import get_claude_ai_oauth_tokens  # type: ignore
        return get_claude_ai_oauth_tokens()
    except ImportError:
        return None


async def _get_organization_uuid() -> Optional[str]:
    try:
        from claude_code.services.oauth.client import get_organization_uuid  # type: ignore
        return await get_organization_uuid()
    except ImportError:
        return None


def _get_base_api_url() -> str:
    try:
        from claude_code.constants.oauth import get_oauth_config  # type: ignore
        return get_oauth_config().get("BASE_API_URL", "https://api.anthropic.com")
    except ImportError:
        return "https://api.anthropic.com"


def _get_oauth_headers(access_token: str) -> Dict[str, str]:
    try:
        from claude_code.utils.teleport.api import get_oauth_headers  # type: ignore
        return get_oauth_headers(access_token)
    except ImportError:
        return {"Authorization": f"Bearer {access_token}"}


async def fetch_environments() -> List[EnvironmentResource]:
    """Fetch the list of available environments from the Environment API."""
    tokens = _get_claude_ai_oauth_tokens()
    access_token = tokens.get("accessToken") if tokens else None
    if not access_token:
        raise RuntimeError(
            "Claude Code web sessions require authentication with a Claude.ai account. "
            "API key authentication is not sufficient. "
            "Please run /login to authenticate."
        )

    org_uuid = await _get_organization_uuid()
    if not org_uuid:
        raise RuntimeError("Unable to get organization UUID")

    url = f"{_get_base_api_url()}/v1/environment_providers"
    headers = {
        **_get_oauth_headers(access_token),
        "x-organization-uuid": org_uuid,
    }

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data.get("environments", [])
    except Exception as exc:
        log.error("fetch_environments error: %s", exc)
        raise RuntimeError(f"Failed to fetch environments: {exc}") from exc


async def create_default_cloud_environment(name: str) -> EnvironmentResource:
    """Create a default anthropic_cloud environment."""
    tokens = _get_claude_ai_oauth_tokens()
    access_token = tokens.get("accessToken") if tokens else None
    if not access_token:
        raise RuntimeError(
            "Authentication required. Please run /login to authenticate."
        )

    org_uuid = await _get_organization_uuid()
    if not org_uuid:
        raise RuntimeError("Unable to get organization UUID")

    url = f"{_get_base_api_url()}/v1/environment_providers"
    headers = {
        **_get_oauth_headers(access_token),
        "x-organization-uuid": org_uuid,
    }
    payload = {"kind": "anthropic_cloud", "name": name}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        log.error("create_default_cloud_environment error: %s", exc)
        raise RuntimeError(f"Failed to create default cloud environment: {exc}") from exc


async def delete_environment(environment_id: str) -> None:
    """Delete an environment by ID."""
    tokens = _get_claude_ai_oauth_tokens()
    access_token = tokens.get("accessToken") if tokens else None
    if not access_token:
        raise RuntimeError("Authentication required.")

    org_uuid = await _get_organization_uuid()
    if not org_uuid:
        raise RuntimeError("Unable to get organization UUID")

    url = f"{_get_base_api_url()}/v1/environment_providers/{environment_id}"
    headers = {
        **_get_oauth_headers(access_token),
        "x-organization-uuid": org_uuid,
    }

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(url, headers=headers)
            resp.raise_for_status()
    except Exception as exc:
        log.error("delete_environment error: %s", exc)
        raise RuntimeError(f"Failed to delete environment: {exc}") from exc
