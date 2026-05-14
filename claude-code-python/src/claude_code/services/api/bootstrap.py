"""Bootstrap API call. Ported from services/api/bootstrap.ts"""
from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Optional


async def fetch_bootstrap_api() -> Optional[Dict[str, Any]]:
    """Fetch bootstrap data from /api/claude_cli/bootstrap.

    Returns parsed response dict with client_data and additional_model_options,
    or None if the call is skipped / fails.
    """
    try:
        from claude_code.utils.privacy_level import is_essential_traffic_only
        if is_essential_traffic_only():
            return None
    except Exception:
        pass

    try:
        from claude_code.utils.model.providers import get_api_provider
        if get_api_provider() != "firstParty":
            return None
    except Exception:
        return None

    try:
        from claude_code.constants.oauth import get_oauth_config, OAUTH_BETA_HEADER
        base_url = get_oauth_config().get("BASE_API_URL", "https://api.anthropic.com")
    except Exception:
        base_url = "https://api.anthropic.com"

    endpoint = f"{base_url}/api/claude_cli/bootstrap"

    headers: Dict[str, str] = {}
    try:
        from claude_code.utils.auth import get_anthropic_api_key, get_claude_ai_oauth_tokens, has_profile_scope
        oauth_tokens = get_claude_ai_oauth_tokens()
        if oauth_tokens and oauth_tokens.get("accessToken") and has_profile_scope():
            headers = {
                "Authorization": f"Bearer {oauth_tokens['accessToken']}",
                "anthropic-beta": OAUTH_BETA_HEADER,
            }
        else:
            api_key = get_anthropic_api_key()
            if api_key:
                headers = {"x-api-key": api_key}
            else:
                return None
    except Exception:
        return None

    try:
        from claude_code.utils.user_agent import get_claude_code_user_agent
        headers["User-Agent"] = get_claude_code_user_agent()
    except Exception:
        pass

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                endpoint,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return {
                    "client_data": data.get("client_data"),
                    "additional_model_options": _parse_model_options(
                        data.get("additional_model_options") or []
                    ),
                }
    except Exception:
        return None


def _parse_model_options(raw: list) -> List[Dict[str, str]]:
    """Transform raw model options into label/value/description dicts."""
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        model = item.get("model", "")
        name = item.get("name", "")
        description = item.get("description", "")
        if model:
            result.append({"value": model, "label": name, "description": description})
    return result


async def apply_bootstrap_to_config(data: Optional[Dict[str, Any]]) -> None:
    """Persist bootstrap client_data to global config if changed."""
    if not data:
        return
    client_data = data.get("client_data")
    if client_data is None:
        return

    try:
        from claude_code.utils.config import get_global_config, save_global_config
        import json

        existing = get_global_config().get("clientData")
        if json.dumps(existing, sort_keys=True) == json.dumps(client_data, sort_keys=True):
            return  # No change

        def _update(cfg: dict) -> dict:
            return {**cfg, "clientData": client_data}

        save_global_config(_update)
    except Exception:
        pass
