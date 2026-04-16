# 原始 TS: services/oauth/index.ts + client.ts + crypto.ts
"""OAuth 2.0 PKCE authorization code flow stub."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Crypto helpers (oauth/crypto.ts)
# ---------------------------------------------------------------------------

def generate_code_verifier(length: int = 64) -> str:
    """Generate a cryptographically-random PKCE code verifier."""
    return base64.urlsafe_b64encode(os.urandom(length)).rstrip(b"=").decode()


def generate_code_challenge(verifier: str) -> str:
    """Derive S256 code challenge from *verifier*."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def generate_state() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Token types
# ---------------------------------------------------------------------------

@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str = ""
    token_type: str = "Bearer"
    expires_in: int = 3600
    scope: str = ""
    # Extra provider metadata
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class OAuthProfile:
    """Decoded profile returned by the userinfo / profile endpoint."""

    account_id: str = ""
    email: str = ""
    display_name: str = ""
    subscription_type: str = ""
    rate_limit_tier: str = ""


# ---------------------------------------------------------------------------
# OAuthService
# ---------------------------------------------------------------------------

class OAuthService:
    """OAuth 2.0 authorization code flow with PKCE.

    TODO: Implement actual HTTP calls to Anthropic / claude.ai endpoints.
    """

    def __init__(self) -> None:
        self._code_verifier = generate_code_verifier()
        self._state = generate_state()
        self._pending_code_resolve: Any = None
        self._port: int | None = None

    def get_auth_url(
        self,
        *,
        login_with_claude_ai: bool = False,
        inference_only: bool = False,
        expires_in: int | None = None,
        org_uuid: str | None = None,
        login_hint: str | None = None,
    ) -> str:
        """Build the OAuth authorization URL.

        TODO: Read real endpoint from oauth config constants.
        """
        challenge = generate_code_challenge(self._code_verifier)
        base = "https://claude.ai/oauth/authorize" if login_with_claude_ai else "https://console.anthropic.com/oauth/authorize"
        params = {
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": self._state,
        }
        if login_hint:
            params["login_hint"] = login_hint
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base}?{query}"

    async def start_oauth_flow(
        self,
        auth_url_handler: Any = None,
        *,
        login_with_claude_ai: bool = False,
        inference_only: bool = False,
    ) -> OAuthTokens:
        """Run the full PKCE OAuth flow and return tokens.

        TODO: Start local callback server, open browser, exchange code.
        """
        url = self.get_auth_url(login_with_claude_ai=login_with_claude_ai, inference_only=inference_only)
        logger.info("OAuth flow started. Auth URL: %s", url)
        if auth_url_handler:
            await auth_url_handler(url)
        # TODO: await authorization code then call exchange_code_for_tokens
        raise NotImplementedError("OAuth flow not yet implemented")

    async def exchange_code_for_tokens(self, code: str) -> OAuthTokens:
        """Exchange authorization code for access/refresh tokens.

        TODO: POST to token endpoint.
        """
        raise NotImplementedError("Token exchange not yet implemented")

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        """Use refresh_token to get a new access token.

        TODO: POST to refresh endpoint.
        """
        raise NotImplementedError("Token refresh not yet implemented")

    async def get_profile(self, access_token: str) -> OAuthProfile:
        """Fetch user profile using the access token.

        TODO: GET /api/oauth/profile with Bearer header.
        """
        raise NotImplementedError("Profile fetch not yet implemented")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def load_stored_tokens() -> OAuthTokens | None:
    """Load persisted OAuth tokens from disk.

    TODO: Read from ~/.claude/auth.json (encrypted).
    """
    return None


def save_tokens(tokens: OAuthTokens) -> None:
    """Persist OAuth tokens to disk.

    TODO: Write to ~/.claude/auth.json (encrypted).
    """
    logger.debug("save_tokens: stub – tokens not persisted")


def clear_tokens() -> None:
    """Remove stored tokens (logout).

    TODO: Delete ~/.claude/auth.json.
    """
    logger.debug("clear_tokens: stub")
