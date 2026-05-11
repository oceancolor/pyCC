"""
services/mcp/claudeai.py — Claude.ai MCP server configs.
Ported from services/mcp/claudeai.ts (164 lines).

Fetches MCP server configurations from Claude.ai org configs.
These servers are managed by the organization via Claude.ai.
Results are memoized for the session lifetime (fetch once per CLI session).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict, Optional

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_S = 5.0
MCP_SERVERS_BETA_HEADER = "mcp-servers-2025-12-04"


# ---------------------------------------------------------------------------
# Lazy helpers
# ---------------------------------------------------------------------------

def _get_oauth_config() -> dict:
    try:
        from claude_code.constants.oauth import get_oauth_config
        return get_oauth_config() or {}
    except (ImportError, Exception):
        return {"BASE_API_URL": "https://api.anthropic.com"}


def _get_claude_ai_oauth_tokens() -> Optional[dict]:
    try:
        from claude_code.utils.auth import get_claude_ai_oauth_tokens
        return get_claude_ai_oauth_tokens()
    except (ImportError, Exception):
        return None


def _is_env_defined_falsy(val) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in ("0", "false", "no", "")


def _log_for_debugging(msg: str) -> None:
    try:
        from claude_code.utils.debug import log_for_debugging
        log_for_debugging(msg)
    except (ImportError, Exception):
        logger.debug(msg)


def _log_event(event_name: str, data: dict) -> None:
    try:
        from claude_code.services.analytics import log_event
        log_event(event_name, data)
    except (ImportError, Exception):
        pass


def _normalize_name_for_mcp(name: str) -> str:
    try:
        from claude_code.services.mcp.normalization import normalize_mcp_server_name
        return normalize_mcp_server_name(name)
    except (ImportError, Exception):
        return name.strip().replace(" ", "_").lower()


def _get_global_config() -> dict:
    try:
        from claude_code.utils.config import get_global_config
        return dict(get_global_config() or {})
    except (ImportError, Exception):
        return {}


def _save_global_config(updater) -> None:
    try:
        from claude_code.utils.config import save_global_config
        save_global_config(updater)
    except (ImportError, Exception):
        pass


def _clear_mcp_auth_cache() -> None:
    try:
        from claude_code.services.mcp.client import clear_mcp_auth_cache
        clear_mcp_auth_cache()
    except (ImportError, Exception):
        pass


# ---------------------------------------------------------------------------
# Main: fetch Claude.ai MCP configs
# ---------------------------------------------------------------------------

# Module-level memoize flag (mimics lodash memoize — one call per session).
_fetch_cache: Optional[Dict[str, dict]] = None
_fetch_done: bool = False


async def fetch_claude_ai_mcp_configs_if_eligible() -> Dict[str, dict]:
    """
    Fetches MCP server configurations from Claude.ai org configs.
    Results are memoized for the session lifetime.
    """
    import os
    global _fetch_cache, _fetch_done

    if _fetch_done:
        return _fetch_cache or {}

    try:
        result = await _do_fetch_claude_ai_mcp_configs()
        _fetch_cache = result
        _fetch_done = True
        return result
    except Exception:
        _fetch_done = True
        _fetch_cache = {}
        return {}


async def _do_fetch_claude_ai_mcp_configs() -> Dict[str, dict]:
    """Internal implementation of the fetch."""
    import os
    import aiohttp  # type: ignore

    env_val = os.environ.get("ENABLE_CLAUDEAI_MCP_SERVERS")
    if _is_env_defined_falsy(env_val):
        _log_for_debugging("[claudeai-mcp] Disabled via env var")
        _log_event("tengu_claudeai_mcp_eligibility", {"state": "disabled_env_var"})
        return {}

    tokens = _get_claude_ai_oauth_tokens()
    if not tokens or not tokens.get("accessToken"):
        _log_for_debugging("[claudeai-mcp] No access token")
        _log_event("tengu_claudeai_mcp_eligibility", {"state": "no_oauth_token"})
        return {}

    # Check for user:mcp_servers scope directly — avoids the non-interactive mode
    # false-negative in isClaudeAISubscriber().
    scopes = tokens.get("scopes") or []
    if "user:mcp_servers" not in scopes:
        scope_str = ",".join(scopes) if scopes else "none"
        _log_for_debugging(
            f"[claudeai-mcp] Missing user:mcp_servers scope (scopes={scope_str})"
        )
        _log_event("tengu_claudeai_mcp_eligibility", {"state": "missing_scope"})
        return {}

    base_url = _get_oauth_config().get("BASE_API_URL", "https://api.anthropic.com")
    url = f"{base_url}/v1/mcp_servers?limit=1000"
    _log_for_debugging(f"[claudeai-mcp] Fetching from {url}")

    try:
        timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT_S)
        headers = {
            "Authorization": f"Bearer {tokens['accessToken']}",
            "Content-Type": "application/json",
            "anthropic-beta": MCP_SERVERS_BETA_HEADER,
            "anthropic-version": "2023-06-01",
        }
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
    except Exception:
        _log_for_debugging("[claudeai-mcp] Fetch failed")
        return {}

    configs: Dict[str, dict] = {}
    used_normalized: set = set()

    for server in data.get("data", []):
        base_name = f"claude.ai {server.get('display_name', '')}"
        final_name = base_name
        final_normalized = _normalize_name_for_mcp(final_name)
        count = 1
        while final_normalized in used_normalized:
            count += 1
            final_name = f"{base_name} ({count})"
            final_normalized = _normalize_name_for_mcp(final_name)
        used_normalized.add(final_normalized)

        configs[final_name] = {
            "type": "claudeai-proxy",
            "url": server.get("url", ""),
            "id": server.get("id", ""),
            "scope": "claudeai",
        }

    _log_for_debugging(f"[claudeai-mcp] Fetched {len(configs)} servers")
    _log_event("tengu_claudeai_mcp_eligibility", {"state": "eligible"})
    return configs


def clear_claude_ai_mcp_configs_cache() -> None:
    """
    Clears the memoized cache for fetch_claude_ai_mcp_configs_if_eligible.
    Call this after login so the next fetch uses the new auth tokens.
    """
    global _fetch_cache, _fetch_done
    _fetch_cache = None
    _fetch_done = False
    _clear_mcp_auth_cache()


def mark_claude_ai_mcp_connected(name: str) -> None:
    """
    Record that a claude.ai connector successfully connected. Idempotent.

    Gates the "N connectors unavailable/need auth" startup notifications.
    """
    def updater(current: dict) -> dict:
        seen = list(current.get("claudeAiMcpEverConnected") or [])
        if name in seen:
            return current
        return {**current, "claudeAiMcpEverConnected": seen + [name]}

    _save_global_config(updater)


def has_claude_ai_mcp_ever_connected(name: str) -> bool:
    """Check if a claude.ai connector has ever successfully connected."""
    return name in (_get_global_config().get("claudeAiMcpEverConnected") or [])
