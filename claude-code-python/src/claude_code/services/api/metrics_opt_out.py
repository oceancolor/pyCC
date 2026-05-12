"""
Metrics opt-out (org-level metrics_logging_enabled) check.
Ported from services/api/metricsOptOut.ts

Two-tier cache: disk (24h) → in-memory (1h). Zero-network on fresh disk.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, TypedDict

log = logging.getLogger(__name__)

CACHE_TTL_MS = 60 * 60 * 1000       # 1h in-memory TTL
DISK_CACHE_TTL_MS = 24 * 60 * 60 * 1000  # 24h disk TTL

# ─── Simple in-process TTL memoization ──────────────────────────────────────

_MEMO_VALUE: Optional[Dict[str, Any]] = None
_MEMO_TIMESTAMP: float = 0.0


class MetricsStatus(TypedDict):
    enabled: bool
    hasError: bool


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _is_essential_traffic_only() -> bool:
    try:
        from claude_code.utils.privacy_level import is_essential_traffic_only  # type: ignore
        return is_essential_traffic_only()
    except ImportError:
        return False


def _get_auth_headers() -> Dict[str, Any]:
    try:
        from claude_code.utils.http import get_auth_headers  # type: ignore
        return get_auth_headers()
    except ImportError:
        return {"error": "Auth module unavailable"}


def _get_claude_code_user_agent() -> str:
    try:
        from claude_code.utils.user_agent import get_claude_code_user_agent  # type: ignore
        return get_claude_code_user_agent()
    except ImportError:
        return "ClaudeCode/0.0.0"


def _get_global_config() -> dict:
    try:
        from claude_code.utils.config import get_global_config  # type: ignore
        return get_global_config() or {}
    except ImportError:
        return {}


def _save_global_config(updater) -> None:
    try:
        from claude_code.utils.config import save_global_config  # type: ignore
        save_global_config(updater)
    except ImportError:
        pass


def _is_claude_ai_subscriber() -> bool:
    try:
        from claude_code.utils.auth import is_claude_ai_subscriber  # type: ignore
        return is_claude_ai_subscriber()
    except ImportError:
        return False


def _has_profile_scope() -> bool:
    try:
        from claude_code.utils.auth import has_profile_scope  # type: ignore
        return has_profile_scope()
    except ImportError:
        return False


async def _fetch_metrics_enabled() -> Dict[str, Any]:
    """Call the Anthropic API to check if metrics are enabled."""
    auth_result = _get_auth_headers()
    if auth_result.get("error"):
        raise RuntimeError(f"Auth error: {auth_result['error']}")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": _get_claude_code_user_agent(),
        **auth_result.get("headers", {}),
    }
    url = "https://api.anthropic.com/api/claude_code/organizations/metrics_enabled"

    import httpx
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _check_metrics_enabled_api() -> MetricsStatus:
    global _MEMO_VALUE, _MEMO_TIMESTAMP

    if _is_essential_traffic_only():
        return {"enabled": False, "hasError": False}

    now_ms = time.monotonic() * 1000
    if _MEMO_VALUE is not None and now_ms - _MEMO_TIMESTAMP < CACHE_TTL_MS:
        return _MEMO_VALUE  # type: ignore[return-value]

    try:
        data = await _fetch_metrics_enabled()
        enabled = bool(data.get("metrics_logging_enabled", False))
        result: MetricsStatus = {"enabled": enabled, "hasError": False}
    except Exception as exc:
        log.debug("Failed to check metrics opt-out status: %s", exc)
        result = {"enabled": False, "hasError": True}

    if not result["hasError"]:
        _MEMO_VALUE = result  # type: ignore[assignment]
        _MEMO_TIMESTAMP = now_ms

    return result


async def _refresh_metrics_status() -> MetricsStatus:
    result = await _check_metrics_enabled_api()
    if result["hasError"]:
        return result

    cached = _get_global_config().get("metricsStatusCache")
    unchanged = cached is not None and cached.get("enabled") == result["enabled"]
    if unchanged and time.time() * 1000 - (cached.get("timestamp", 0)) < DISK_CACHE_TTL_MS:
        return result

    def _update(current: dict) -> dict:
        return {
            **current,
            "metricsStatusCache": {
                "enabled": result["enabled"],
                "timestamp": int(time.time() * 1000),
            },
        }

    _save_global_config(_update)
    return result


async def check_metrics_enabled() -> MetricsStatus:
    """Check if metrics are enabled for the current organization.

    Returns ``{"enabled": bool, "hasError": bool}``.
    """
    if _is_claude_ai_subscriber() and not _has_profile_scope():
        return {"enabled": False, "hasError": False}

    cached = _get_global_config().get("metricsStatusCache")
    if cached:
        if time.time() * 1000 - cached.get("timestamp", 0) > DISK_CACHE_TTL_MS:
            asyncio.ensure_future(_refresh_metrics_status())
        return {"enabled": bool(cached.get("enabled", False)), "hasError": False}

    return await _refresh_metrics_status()


def _clear_metrics_enabled_cache_for_testing() -> None:
    """Clear in-memory cache. For testing only."""
    global _MEMO_VALUE, _MEMO_TIMESTAMP
    _MEMO_VALUE = None
    _MEMO_TIMESTAMP = 0.0
