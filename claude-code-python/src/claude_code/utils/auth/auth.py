# 原始 TS: utils/auth.ts
"""Core authentication utilities: API key, OAuth token, subscription type."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Optional


class SubscriptionType(str, Enum):
    FREE = "free"
    PRO = "pro"
    MAX = "max"
    TEAM = "team"
    ENTERPRISE = "enterprise"


@dataclass
class AuthTokenSource:
    """Describes the current authentication token source."""
    has_token: bool = False
    source: str = ""  # "env", "config", "oauth", "fd", ""
    is_oauth: bool = False
    subscription_type: Optional[SubscriptionType] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_api_key_from_env() -> Optional[str]:
    """Return ANTHROPIC_API_KEY from environment, or None."""
    return os.environ.get("ANTHROPIC_API_KEY") or None


def _get_api_key_from_config() -> Optional[str]:
    """Return the API key stored in the global config file, or None.

    Avoids circular imports by lazily importing config.
    """
    try:
        from claude_code.utils.settings import get_global_config  # type: ignore
        cfg = get_global_config()
        return getattr(cfg, "api_key", None) or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_anthropic_api_key() -> Optional[str]:
    """Return the active Anthropic API key, or None if not set.

    Priority: ANTHROPIC_API_KEY env var → global config.
    """
    return _get_api_key_from_env() or _get_api_key_from_config()


def get_auth_token_source() -> AuthTokenSource:
    """Return metadata describing where the active auth token came from."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AuthTokenSource(has_token=True, source="env")

    cfg_key = _get_api_key_from_config()
    if cfg_key:
        return AuthTokenSource(has_token=True, source="config")

    # TODO: check OAuth token from config/file-descriptor
    return AuthTokenSource(has_token=False, source="")


def get_subscription_type() -> Optional[SubscriptionType]:
    """Return the current subscription type, or None if unknown."""
    # TODO: read from OAuth token claims or config
    return None


def is_claude_ai_subscriber() -> bool:
    """Return True if the user is authenticated via claude.ai subscription."""
    src = get_auth_token_source()
    return src.is_oauth and src.subscription_type is not None
