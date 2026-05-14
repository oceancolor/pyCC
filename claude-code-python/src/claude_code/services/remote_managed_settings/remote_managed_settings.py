"""Remote managed settings. Ported from services/remoteManagedSettings (fuller implementation)."""
from __future__ import annotations
from typing import Any, Dict, Optional
import json


_settings_cache: Optional[Dict[str, Any]] = None


async def load_remote_managed_settings() -> Optional[Dict[str, Any]]:
    """Load remote managed settings from the API. Returns None on failure."""
    global _settings_cache

    try:
        from claude_code.utils.model.providers import get_api_provider
        if get_api_provider() != "firstParty":
            return None
    except Exception:
        return None

    try:
        from claude_code.constants.oauth import get_oauth_config
        cfg = get_oauth_config()
        base_url = cfg.get("BASE_API_URL", "https://api.anthropic.com")
    except Exception:
        base_url = "https://api.anthropic.com"

    endpoint = f"{base_url}/api/claude_code/remote_managed_settings"

    try:
        import aiohttp
        from claude_code.utils.auth import get_anthropic_api_key
        api_key = get_anthropic_api_key() or ""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                endpoint,
                headers={"x-api-key": api_key},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    settings = data.get("settings") or {}
                    _settings_cache = settings
                    return settings
    except Exception:
        pass
    return None


def clear_remote_managed_settings_cache() -> None:
    """Clear the in-memory settings cache."""
    global _settings_cache
    _settings_cache = None


async def get_remote_managed_settings() -> Dict[str, Any]:
    """Return remote managed settings (from cache or fresh fetch)."""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    result = await load_remote_managed_settings()
    return result or {}
