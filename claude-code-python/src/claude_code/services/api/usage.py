"""Claude AI usage/utilization API.

Ported from services/api/usage.ts
"""
from __future__ import annotations

import os
from typing import Optional, TypedDict

# ---------------------------------------------------------------------------
# TypedDicts (mirrors TS exported types)
# ---------------------------------------------------------------------------


class RateLimit(TypedDict, total=False):
    """Mirrors RateLimit type in usage.ts."""
    utilization: Optional[float]  # 0–100 percentage
    resets_at: Optional[str]      # ISO 8601 timestamp


class ExtraUsage(TypedDict, total=False):
    """Mirrors ExtraUsage type in usage.ts."""
    is_enabled: bool
    monthly_limit: Optional[float]
    used_credits: Optional[float]
    utilization: Optional[float]


class Utilization(TypedDict, total=False):
    """Mirrors Utilization type in usage.ts."""
    five_hour: Optional[RateLimit]
    seven_day: Optional[RateLimit]
    seven_day_oauth_apps: Optional[RateLimit]
    seven_day_opus: Optional[RateLimit]
    seven_day_sonnet: Optional[RateLimit]
    extra_usage: Optional[ExtraUsage]


# ---------------------------------------------------------------------------
# fetch_utilization
# ---------------------------------------------------------------------------


async def fetch_utilization() -> Optional[Utilization]:
    """Fetch rate-limit utilization from the Claude API.

    Mirrors fetchUtilization() in usage.ts.

    Returns:
        Utilization dict on success, empty dict when the user is not a
        subscriber / lacks profile scope, or None if the OAuth token is
        expired (avoids 401 noise).

    Raises:
        Exception: propagated auth errors from get_auth_headers().
    """
    # Guard: only run for ClaudeAI subscribers with profile scope
    try:
        from claude_code.utils.auth import (
            is_claude_ai_subscriber,
            has_profile_scope,
            get_claude_ai_oauth_tokens,
        )
        if not is_claude_ai_subscriber() or not has_profile_scope():
            return {}

        # Skip API call if OAuth token is expired to avoid 401 errors
        tokens = get_claude_ai_oauth_tokens()
    except ImportError:
        # Auth utilities not available — skip silently
        return {}

    if tokens is not None:
        try:
            from claude_code.services.oauth.client import is_oauth_token_expired
            if is_oauth_token_expired(tokens.get("expires_at") or tokens.get("expiresAt")):
                return None
        except ImportError:
            pass

    # Build request headers
    try:
        from claude_code.utils.http import get_auth_headers
        auth_result = get_auth_headers()
        if isinstance(auth_result, dict) and auth_result.get("error"):
            raise Exception(f"Auth error: {auth_result['error']}")
        headers_extra = auth_result if isinstance(auth_result, dict) else {}
    except ImportError:
        headers_extra = {}

    try:
        from claude_code.utils.user_agent import get_claude_code_user_agent
        user_agent = get_claude_code_user_agent()
    except ImportError:
        user_agent = "ClaudeCode/0.0.0"

    # Build base URL
    try:
        from claude_code.constants.oauth import get_oauth_config
        base_api_url = get_oauth_config().get("BASE_API_URL", "https://claude.ai")
    except ImportError:
        base_api_url = os.environ.get("ANTHROPIC_BASE_URL", "https://claude.ai")

    url = f"{base_api_url}/api/oauth/usage"

    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": user_agent,
        **headers_extra,
    }

    # Perform HTTP GET — try aiohttp first, fall back to urllib
    timeout_s = 5.0  # 5 second timeout (matches TS)

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        return _normalize_utilization(data)

    except ImportError:
        pass  # aiohttp not available, try httpx

    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = client.get(url, headers=request_headers)
            if hasattr(resp, "__await__"):
                resp = await resp  # type: ignore[misc]
            resp.raise_for_status()
            data = resp.json()
        return _normalize_utilization(data)

    except ImportError:
        pass  # httpx not available, fall back to synchronous urllib

    # Synchronous fallback (urllib.request — no async)
    import json
    import urllib.request

    req = urllib.request.Request(url, headers=request_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
        data = json.loads(raw)
        return _normalize_utilization(data)
    except Exception:
        raise


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_utilization(data: object) -> Utilization:
    """Coerce arbitrary JSON response to a Utilization TypedDict.

    The API returns camelCase keys; we normalise to snake_case where needed
    while preserving the structure expected by callers.
    """
    if not isinstance(data, dict):
        return {}

    result: Utilization = {}

    def _parse_rate_limit(raw: object) -> Optional[RateLimit]:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            return None
        return RateLimit(
            utilization=raw.get("utilization"),
            resets_at=raw.get("resets_at") or raw.get("resetsAt"),
        )

    def _parse_extra_usage(raw: object) -> Optional[ExtraUsage]:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            return None
        return ExtraUsage(
            is_enabled=bool(raw.get("is_enabled", raw.get("isEnabled", False))),
            monthly_limit=raw.get("monthly_limit") or raw.get("monthlyLimit"),
            used_credits=raw.get("used_credits") or raw.get("usedCredits"),
            utilization=raw.get("utilization"),
        )

    for py_key, ts_key in (
        ("five_hour",         "five_hour"),
        ("seven_day",         "seven_day"),
        ("seven_day_oauth_apps", "seven_day_oauth_apps"),
        ("seven_day_opus",    "seven_day_opus"),
        ("seven_day_sonnet",  "seven_day_sonnet"),
    ):
        raw_val = data.get(py_key) or data.get(ts_key)
        if raw_val is not None or py_key in data or ts_key in data:
            result[py_key] = _parse_rate_limit(raw_val)  # type: ignore[literal-required]

    extra_raw = data.get("extra_usage") or data.get("extraUsage")
    if extra_raw is not None or "extra_usage" in data or "extraUsage" in data:
        result["extra_usage"] = _parse_extra_usage(extra_raw)

    return result
