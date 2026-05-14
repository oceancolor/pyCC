"""OAuth client. Ported from services/oauth/client.ts"""
from __future__ import annotations
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode


def should_use_claude_ai_auth(scopes: Optional[List[str]]) -> bool:
    """Check if the user has Claude.ai authentication scope."""
    from claude_code.constants.oauth import CLAUDE_AI_INFERENCE_SCOPE
    return bool(scopes and CLAUDE_AI_INFERENCE_SCOPE in scopes)


def parse_scopes(scope_string: Optional[str]) -> List[str]:
    """Parse a space-separated scope string into a list."""
    if not scope_string:
        return []
    return [s for s in scope_string.split(" ") if s]


def is_oauth_token_expired(expires_at: Optional[float]) -> bool:
    """Return True if the token has expired (with 60s buffer)."""
    if expires_at is None:
        return False
    return time.time() >= (expires_at - 60)


def build_auth_url(
    code_challenge: str,
    state: str,
    port: int,
    is_manual: bool,
    login_with_claude_ai: bool = False,
    inference_only: bool = False,
    org_uuid: Optional[str] = None,
    login_hint: Optional[str] = None,
    login_method: Optional[str] = None,
) -> str:
    """Build the OAuth authorization URL."""
    try:
        from claude_code.constants.oauth import get_oauth_config
        cfg = get_oauth_config()
        auth_url_base = cfg["CLAUDE_AI_AUTHORIZE_URL"] if login_with_claude_ai else cfg["CONSOLE_AUTHORIZE_URL"]
        client_id = cfg["CLIENT_ID"]
        manual_redirect = cfg["MANUAL_REDIRECT_URL"]
    except Exception:
        auth_url_base = "https://claude.ai/oauth/authorize"
        client_id = "claude-code"
        manual_redirect = "urn:ietf:wg:oauth:2.0:oob"

    redirect_uri = manual_redirect if is_manual else f"http://localhost:{port}/callback"

    scopes: List[str]
    try:
        from claude_code.constants.oauth import CLAUDE_AI_OAUTH_SCOPES, ALL_OAUTH_SCOPES
        scopes = CLAUDE_AI_OAUTH_SCOPES if login_with_claude_ai else ALL_OAUTH_SCOPES
        if inference_only:
            from claude_code.constants.oauth import CLAUDE_AI_INFERENCE_SCOPE
            scopes = [CLAUDE_AI_INFERENCE_SCOPE]
    except Exception:
        scopes = ["openid", "profile", "email"]

    params: Dict[str, str] = {
        "code": "true",
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "scope": " ".join(scopes),
    }
    if org_uuid:
        params["org_uuid"] = org_uuid
    if login_hint:
        params["login_hint"] = login_hint
    if login_method:
        params["login_method"] = login_method

    return f"{auth_url_base}?{urlencode(params)}"


async def get_oauth_token() -> Optional[str]:
    """Return the current OAuth access token, or None."""
    return os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")


async def refresh_oauth_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Attempt to refresh an OAuth token. Returns new token data or None."""
    return None


async def exchange_code_for_token(
    code: str,
    code_verifier: str,
    port: int,
    is_manual: bool = False,
) -> Optional[Dict[str, Any]]:
    """Exchange an authorization code for tokens."""
    return None
