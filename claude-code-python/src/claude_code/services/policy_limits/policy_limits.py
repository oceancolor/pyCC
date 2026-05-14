"""Policy limits. Ported from services/policyLimits/index.ts

Fetches organization-level policy restrictions from the API and uses them
to disable CLI features. Fails open — if fetch fails, continues without restrictions.
"""
from __future__ import annotations
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

_CACHE_FILENAME = "policy-limits.json"
_FETCH_TIMEOUT_S = 10
_DEFAULT_MAX_RETRIES = 5
_POLLING_INTERVAL_S = 3600  # 1 hour
_LOADING_PROMISE_TIMEOUT_S = 30

# Policies that default to denied in essential-traffic-only mode
_ESSENTIAL_TRAFFIC_DENY_ON_MISS = {"allow_product_feedback"}

# Session-level cache
_session_cache: Optional[Dict[str, Any]] = None
_loading_event: Optional[asyncio.Event] = None
_polling_task: Optional[asyncio.Task] = None


def _get_cache_path() -> Path:
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir
        return Path(get_claude_config_home_dir()) / _CACHE_FILENAME
    except Exception:
        return Path.home() / ".claude" / _CACHE_FILENAME


def is_policy_limits_eligible() -> bool:
    """Check if the current user is eligible for policy limits. Fails open."""
    try:
        from claude_code.utils.model.providers import get_api_provider, is_first_party_anthropic_base_url
        if get_api_provider() != "firstParty":
            return False
        if not is_first_party_anthropic_base_url():
            return False
    except Exception:
        return False

    # Console API key users
    try:
        from claude_code.utils.auth import get_anthropic_api_key
        if get_anthropic_api_key():
            return True
    except Exception:
        pass

    return False


def _load_cached_restrictions() -> Optional[Dict[str, Any]]:
    """Load restrictions from the on-disk cache synchronously."""
    try:
        cache_path = _get_cache_path()
        if not cache_path.exists():
            return None
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return data.get("restrictions")
    except Exception:
        return None


async def _save_cached_restrictions(restrictions: Dict[str, Any]) -> None:
    """Save restrictions to the on-disk cache."""
    try:
        cache_path = _get_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"restrictions": restrictions}, indent=2),
            encoding="utf-8",
        )
        cache_path.chmod(0o600)
    except Exception:
        pass


async def _fetch_policy_limits_once() -> Optional[Dict[str, Any]]:
    """Fetch policy limits from the API (single attempt)."""
    try:
        from claude_code.constants.oauth import get_oauth_config
        cfg = get_oauth_config()
        base_url = cfg.get("BASE_API_URL", "https://api.anthropic.com")
    except Exception:
        base_url = "https://api.anthropic.com"

    endpoint = f"{base_url}/api/claude_code/policy_limits"

    headers: Dict[str, str] = {}
    try:
        from claude_code.utils.auth import get_anthropic_api_key
        api_key = get_anthropic_api_key()
        if api_key:
            headers["x-api-key"] = api_key
    except Exception:
        pass

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                endpoint,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=_FETCH_TIMEOUT_S),
                allow_redirects=True,
            ) as resp:
                if resp.status == 304:
                    return None  # cache still valid
                if resp.status == 404:
                    return {}  # no restrictions
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("restrictions", {})
    except Exception:
        pass
    return None


async def _fetch_and_load() -> Optional[Dict[str, Any]]:
    """Fetch policy limits, apply caching, and update session cache."""
    global _session_cache

    if not is_policy_limits_eligible():
        return None

    cached = _load_cached_restrictions()

    result = await _fetch_policy_limits_once()

    if result is None:
        # 304 or error — use cached
        if cached is not None:
            _session_cache = cached
        return cached

    _session_cache = result
    if result:
        await _save_cached_restrictions(result)
    else:
        try:
            _get_cache_path().unlink(missing_ok=True)
        except Exception:
            pass
    return result


def get_restrictions_from_cache() -> Optional[Dict[str, Any]]:
    """Get restrictions synchronously from session or file cache."""
    global _session_cache
    if not is_policy_limits_eligible():
        return None
    if _session_cache is not None:
        return _session_cache
    cached = _load_cached_restrictions()
    if cached is not None:
        _session_cache = cached
    return cached


def is_policy_allowed(policy: str) -> bool:
    """Check if a specific policy action is allowed. Fails open."""
    restrictions = get_restrictions_from_cache()
    if restrictions is None:
        try:
            from claude_code.utils.privacy_level import is_essential_traffic_only
            if is_essential_traffic_only() and policy in _ESSENTIAL_TRAFFIC_DENY_ON_MISS:
                return False
        except Exception:
            pass
        return True  # fail open
    restriction = restrictions.get(policy)
    if restriction is None:
        return True
    return bool(restriction.get("allowed", True))


async def load_policy_limits() -> None:
    """Load policy limits during CLI initialization."""
    global _loading_event
    _loading_event = asyncio.Event()
    try:
        await _fetch_and_load()
    finally:
        _loading_event.set()


async def wait_for_policy_limits_to_load() -> None:
    """Wait for the initial policy limits loading to complete."""
    if _loading_event is not None:
        try:
            await asyncio.wait_for(_loading_event.wait(), timeout=_LOADING_PROMISE_TIMEOUT_S)
        except asyncio.TimeoutError:
            pass


async def refresh_policy_limits() -> None:
    """Refresh policy limits (e.g. after auth state change)."""
    global _session_cache
    _session_cache = None
    try:
        _get_cache_path().unlink(missing_ok=True)
    except Exception:
        pass
    await _fetch_and_load()


async def clear_policy_limits_cache() -> None:
    """Clear all policy limits state."""
    global _session_cache, _polling_task
    _session_cache = None
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        _polling_task = None
    try:
        _get_cache_path().unlink(missing_ok=True)
    except Exception:
        pass


# Legacy/compat stubs
def get_policy_limits() -> Dict[str, Any]:
    return get_restrictions_from_cache() or {}


def check_policy_limit(feature: str) -> bool:
    return is_policy_allowed(feature)
