"""Remote setup API utilities.

Ported from commands/remote-setup/api.ts
Provides helpers for the /web-setup command: GitHub token import,
default environment creation, and OAuth sign-in check.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional, Union

logger = logging.getLogger(__name__)

_CCR_BYOC_BETA_HEADER = "ccr-byoc-2025-07-29"


class RedactedGithubToken:
    """GitHub token wrapper that redacts itself in logs and repr.

    Call ``.reveal()`` only at the single call-site where the raw value
    must appear in an HTTP request body.
    """

    __slots__ = ("_value",)

    def __init__(self, raw: str) -> None:
        self._value = raw

    def reveal(self) -> str:
        """Return the actual token value."""
        return self._value

    def __repr__(self) -> str:
        return "[REDACTED:gh-token]"

    def __str__(self) -> str:
        return "[REDACTED:gh-token]"


# ── Result types ──────────────────────────────────────────────────────────────

ImportTokenResult = Dict[str, str]  # {"github_username": str}

ImportTokenError = Union[
    Dict[Literal["kind"], Literal["not_signed_in"]],
    Dict[Literal["kind"], Literal["invalid_token"]],
    Dict[str, Any],  # server / network errors carry extra fields
]


async def import_github_token(
    token: RedactedGithubToken,
) -> Dict[str, Any]:
    """POST a GitHub token to the CCR backend for validation and storage.

    The backend validates the token against GitHub's /user endpoint and
    stores it encrypted.  On success the token satisfies the same read
    paths as an OAuth token, so clone/push in claude.ai/code works
    immediately.

    Returns:
        ``{"ok": True, "result": {"github_username": ...}}`` on success,
        or ``{"ok": False, "error": {"kind": <reason>}}`` on failure.
        Possible *kind* values: ``not_signed_in``, ``invalid_token``,
        ``server``, ``network``.
    """
    try:
        import aiohttp  # type: ignore
    except ImportError:
        logger.debug("aiohttp not available – remote setup token import skipped")
        return {"ok": False, "error": {"kind": "network"}}

    try:
        from claude_code.utils.auth import prepare_api_request, get_oauth_headers  # type: ignore
        from claude_code.constants import get_oauth_config  # type: ignore
    except ImportError:
        return {"ok": False, "error": {"kind": "not_signed_in"}}

    try:
        access_token, org_uuid = await prepare_api_request()
    except Exception:
        return {"ok": False, "error": {"kind": "not_signed_in"}}

    oauth_cfg = get_oauth_config()
    url = f"{oauth_cfg['BASE_API_URL']}/v1/code/github/import-token"
    headers = {
        **get_oauth_headers(access_token),
        "anthropic-beta": _CCR_BYOC_BETA_HEADER,
        "x-organization-uuid": org_uuid,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"token": token.reveal()},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return {"ok": True, "result": result}
                if resp.status == 400:
                    return {"ok": False, "error": {"kind": "invalid_token"}}
                if resp.status == 401:
                    return {"ok": False, "error": {"kind": "not_signed_in"}}
                logger.error("import-token returned %s", resp.status)
                return {"ok": False, "error": {"kind": "server", "status": resp.status}}
    except Exception as exc:
        logger.debug("import-token network error: %s", exc)
        return {"ok": False, "error": {"kind": "network"}}


async def create_default_environment() -> bool:
    """Create a default cloud environment for first-time users.

    Mirrors the web onboarding default environment request.  Idempotent:
    if an environment already exists the call succeeds immediately.

    Returns:
        ``True`` when the environment existed or was created; ``False`` on error.
    """
    try:
        from claude_code.utils.auth import prepare_api_request, get_oauth_headers  # type: ignore
        from claude_code.constants import get_oauth_config  # type: ignore
    except ImportError:
        return False

    try:
        access_token, org_uuid = await prepare_api_request()
    except Exception:
        return False

    # Skip if there are already environments
    try:
        from claude_code.utils.teleport.environment_selection import fetch_environments  # type: ignore
        envs = await fetch_environments()
        if envs:
            return True
    except Exception:
        pass

    try:
        import aiohttp  # type: ignore
    except ImportError:
        return False

    oauth_cfg = get_oauth_config()
    url = f"{oauth_cfg['BASE_API_URL']}/v1/environment_providers/cloud/create"
    headers = {
        **get_oauth_headers(access_token),
        "x-organization-uuid": org_uuid,
    }
    payload = {
        "name": "Default",
        "kind": "anthropic_cloud",
        "description": "Default - trusted network access",
        "config": {
            "environment_type": "anthropic",
            "cwd": "/home/user",
            "init_script": None,
            "environment": {},
            "languages": [
                {"name": "python", "version": "3.11"},
                {"name": "node", "version": "20"},
            ],
            "network_config": {
                "allowed_hosts": [],
                "allow_default_hosts": True,
            },
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                return resp.status // 100 == 2
    except Exception:
        return False


async def is_signed_in() -> bool:
    """Return ``True`` when the user has valid Claude OAuth credentials."""
    try:
        from claude_code.utils.auth import prepare_api_request  # type: ignore
        await prepare_api_request()
        return True
    except Exception:
        return False


def get_code_web_url() -> str:
    """Return the base URL for claude.ai/code."""
    try:
        from claude_code.constants import get_oauth_config  # type: ignore
        cfg = get_oauth_config()
        return f"{cfg['CLAUDE_AI_ORIGIN']}/code"
    except Exception:
        return "https://claude.ai/code"


# ── Legacy compat stubs ───────────────────────────────────────────────────────

async def create_remote_setup_token() -> Optional[str]:
    """Legacy: return a setup token for the /web-setup flow (deprecated)."""
    signed_in = await is_signed_in()
    if not signed_in:
        return None
    # Real implementation would create/return a short-lived token
    return None


async def verify_remote_setup(token: str) -> bool:
    """Legacy: verify a /web-setup token (deprecated)."""
    return False
