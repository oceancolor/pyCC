"""
Admin request API (limit increase / seat upgrade).
Ported from services/api/adminRequests.ts
"""
from __future__ import annotations

import logging
from typing import Dict, List, Literal, Optional, TypedDict, Union

log = logging.getLogger(__name__)

AdminRequestType = Literal["limit_increase", "seat_upgrade"]
AdminRequestStatus = Literal["pending", "approved", "dismissed"]


class AdminRequestSeatUpgradeDetails(TypedDict, total=False):
    message: Optional[str]
    current_seat_tier: Optional[str]


class AdminRequest(TypedDict):
    uuid: str
    status: AdminRequestStatus
    requester_uuid: Optional[str]
    created_at: str
    request_type: AdminRequestType
    details: Optional[AdminRequestSeatUpgradeDetails]


async def _prepare_api_request() -> Dict[str, str]:
    try:
        from claude_code.utils.teleport.api import prepare_api_request  # type: ignore
        return await prepare_api_request()
    except ImportError:
        return {}


def _get_oauth_headers(access_token: str) -> Dict[str, str]:
    try:
        from claude_code.utils.teleport.api import get_oauth_headers  # type: ignore
        return get_oauth_headers(access_token)
    except ImportError:
        return {"Authorization": f"Bearer {access_token}"}


def _get_base_api_url() -> str:
    try:
        from claude_code.constants.oauth import get_oauth_config  # type: ignore
        return get_oauth_config().get("BASE_API_URL", "https://api.anthropic.com")
    except ImportError:
        return "https://api.anthropic.com"


async def create_admin_request(params: dict) -> AdminRequest:
    """Create an admin request (limit increase or seat upgrade).

    If a pending request of the same type already exists for this user,
    returns the existing request instead of creating a new one.
    """
    ctx = await _prepare_api_request()
    access_token = ctx.get("accessToken", "")
    org_uuid = ctx.get("orgUUID", "")

    headers = {
        **_get_oauth_headers(access_token),
        "x-organization-uuid": org_uuid,
    }
    url = f"{_get_base_api_url()}/api/oauth/organizations/{org_uuid}/admin_requests"

    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=params)
        resp.raise_for_status()
        return resp.json()


async def get_my_admin_requests(
    request_type: AdminRequestType,
    statuses: List[AdminRequestStatus],
) -> Optional[List[AdminRequest]]:
    """Get pending admin requests of a specific type for the current user."""
    ctx = await _prepare_api_request()
    access_token = ctx.get("accessToken", "")
    org_uuid = ctx.get("orgUUID", "")

    headers = {
        **_get_oauth_headers(access_token),
        "x-organization-uuid": org_uuid,
    }
    base = f"{_get_base_api_url()}/api/oauth/organizations/{org_uuid}/admin_requests/me"
    url = f"{base}?request_type={request_type}"
    for status in statuses:
        url += f"&statuses={status}"

    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def check_admin_request_eligibility(
    request_type: AdminRequestType,
) -> Optional[dict]:
    """Check if a specific admin request type is allowed for this org."""
    ctx = await _prepare_api_request()
    access_token = ctx.get("accessToken", "")
    org_uuid = ctx.get("orgUUID", "")

    headers = {
        **_get_oauth_headers(access_token),
        "x-organization-uuid": org_uuid,
    }
    url = (
        f"{_get_base_api_url()}/api/oauth/organizations/{org_uuid}"
        f"/admin_requests/eligibility?request_type={request_type}"
    )

    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()
