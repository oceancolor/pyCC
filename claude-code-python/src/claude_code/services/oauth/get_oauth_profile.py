"""OAuth profile fetcher. Ported from services/oauth/getOauthProfile.ts"""
from __future__ import annotations
from typing import Any, Dict, Optional


async def get_oauth_profile_from_oauth_token(access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch the OAuth profile using an access token."""
    try:
        from claude_code.constants.oauth import get_oauth_config
        cfg = get_oauth_config()
        base_url = cfg.get("BASE_API_URL", "https://api.anthropic.com")
    except Exception:
        base_url = "https://api.anthropic.com"

    endpoint = f"{base_url}/api/oauth/profile"

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                endpoint,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None


async def get_oauth_profile_from_api_key() -> Optional[Dict[str, Any]]:
    """Fetch the OAuth profile using the stored API key."""
    try:
        from claude_code.utils.auth import get_anthropic_api_key
        from claude_code.utils.config import get_global_config
        from claude_code.constants.oauth import get_oauth_config, OAUTH_BETA_HEADER

        config = get_global_config()
        account_uuid = (config.get("oauthAccount") or {}).get("accountUuid")
        api_key = get_anthropic_api_key()

        if not account_uuid or not api_key:
            return None

        cfg = get_oauth_config()
        base_url = cfg.get("BASE_API_URL", "https://api.anthropic.com")
        endpoint = f"{base_url}/api/claude_cli_profile"

        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                endpoint,
                headers={
                    "x-api-key": api_key,
                    "anthropic-beta": OAUTH_BETA_HEADER,
                },
                params={"account_uuid": account_uuid},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None


# Convenience alias matching old stub signature
async def get_oauth_profile(token: str) -> Optional[Dict[str, Any]]:
    return await get_oauth_profile_from_oauth_token(token)
