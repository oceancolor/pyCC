"""
Fetch and store Claude Code first token date.
Ported from services/api/firstTokenDate.ts
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


async def fetch_and_store_claude_code_first_token_date() -> None:
    """Fetch the user's first Claude Code token date and store in global config.

    Called after successful login to cache when the user started using Claude Code.
    No-op if the date is already stored.
    """
    try:
        from claude_code.utils.config import get_global_config, save_global_config  # type: ignore

        config = get_global_config()
        if config.get("claudeCodeFirstTokenDate") is not None:
            return

        try:
            from claude_code.utils.http import get_auth_headers  # type: ignore
            auth_result = get_auth_headers()
            if auth_result.get("error"):
                log.error("Failed to get auth headers: %s", auth_result["error"])
                return
            headers = auth_result.get("headers", {})
        except ImportError:
            return

        try:
            from claude_code.constants.oauth import get_oauth_config  # type: ignore
            oauth_config = get_oauth_config()
            base_url = oauth_config.get("BASE_API_URL", "https://api.anthropic.com")
        except ImportError:
            base_url = "https://api.anthropic.com"

        try:
            from claude_code.utils.user_agent import get_claude_code_user_agent  # type: ignore
            headers["User-Agent"] = get_claude_code_user_agent()
        except ImportError:
            pass

        import httpx

        url = f"{base_url}/api/organization/claude_code_first_token_date"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        first_token_date = data.get("first_token_date") if data else None

        if first_token_date is not None:
            from datetime import datetime

            try:
                datetime.fromisoformat(str(first_token_date).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                log.error(
                    "Received invalid first_token_date from API: %s",
                    first_token_date,
                )
                return

        def _updater(current: dict) -> dict:
            return {**current, "claudeCodeFirstTokenDate": first_token_date}

        save_global_config(_updater)

    except Exception as exc:
        log.error("fetch_and_store_claude_code_first_token_date error: %s", exc)
