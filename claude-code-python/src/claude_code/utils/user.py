"""
User data utilities for Claude Code.

Provides core user data (device ID, session ID, email, platform info)
used across analytics providers and feature flags.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class GitHubActionsMetadata:
    actor: Optional[str] = None
    actor_id: Optional[str] = None
    repository: Optional[str] = None
    repository_id: Optional[str] = None
    repository_owner: Optional[str] = None
    repository_owner_id: Optional[str] = None


@dataclass
class CoreUserData:
    device_id: str
    session_id: str
    app_version: str
    platform: str
    email: Optional[str] = None
    organization_uuid: Optional[str] = None
    account_uuid: Optional[str] = None
    user_type: Optional[str] = None
    subscription_type: Optional[str] = None
    rate_limit_tier: Optional[str] = None
    first_token_time: Optional[int] = None
    github_actions_metadata: Optional[GitHubActionsMetadata] = None


# ---------------------------------------------------------------------------
# Module-level email cache (mirrors TS cachedEmail pattern)
# ---------------------------------------------------------------------------

_cached_email: Optional[str] = None          # None = not fetched yet
_email_fetched: bool = False


def _is_env_truthy(value: Optional[str]) -> bool:
    return bool(value and value.lower() not in ("0", "false", "no", ""))


# ---------------------------------------------------------------------------
# Git email helper
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_git_email() -> Optional[str]:
    """
    Get the user's git email from ``git config user.email``.
    Cached so the subprocess only spawns once per process.
    """
    try:
        result = subprocess.run(
            ["git", "config", "--get", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Email resolution
# ---------------------------------------------------------------------------

def _get_email_sync() -> Optional[str]:
    """Synchronous email lookup — returns cached value or OAuth email."""
    global _cached_email, _email_fetched
    if _email_fetched:
        return _cached_email

    # Ant-only COO_CREATOR fallback
    if os.environ.get("USER_TYPE") == "ant":
        coo = os.environ.get("COO_CREATOR")
        if coo:
            return f"{coo}@anthropic.com"

    return None


async def init_user() -> None:
    """
    Initialize user data asynchronously.
    Pre-fetches email so get_core_user_data() can remain synchronous.
    """
    global _cached_email, _email_fetched
    if not _email_fetched:
        _cached_email = await _get_email_async()
        _email_fetched = True
        get_core_user_data.cache_clear()  # type: ignore[attr-defined]


async def _get_email_async() -> Optional[str]:
    """Async email resolution — tries git config as final fallback."""
    if os.environ.get("USER_TYPE") == "ant":
        coo = os.environ.get("COO_CREATOR")
        if coo:
            return f"{coo}@anthropic.com"
        # Run git config in an executor to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, get_git_email)
    return None


def reset_user_cache() -> None:
    """Reset all user data caches (call on auth changes: login/logout/switch)."""
    global _cached_email, _email_fetched
    _cached_email = None
    _email_fetched = False
    get_core_user_data.cache_clear()  # type: ignore[attr-defined]
    get_git_email.cache_clear()


# ---------------------------------------------------------------------------
# Core user data
# ---------------------------------------------------------------------------

@lru_cache(maxsize=2)
def get_core_user_data(include_analytics_metadata: bool = False) -> CoreUserData:
    """
    Get core user data.

    This is the base representation transformed for different analytics
    providers.  Memoised — call reset_user_cache() to invalidate.
    """
    from claude_code.utils.config import get_or_create_user_id, get_global_config  # noqa: PLC0415

    device_id = get_or_create_user_id()
    session_id = os.environ.get("CLAUDE_SESSION_ID", f"pid-{os.getpid()}")
    app_version = os.environ.get("CLAUDE_VERSION", "unknown")
    platform = _get_platform()

    subscription_type: Optional[str] = None
    rate_limit_tier: Optional[str] = None
    first_token_time: Optional[int] = None

    if include_analytics_metadata:
        try:
            from claude_code.utils.auth import get_subscription_type, get_rate_limit_tier  # noqa: PLC0415
            subscription_type = get_subscription_type()
            rate_limit_tier = get_rate_limit_tier()
        except ImportError:
            pass

    # GitHub Actions metadata
    github_meta: Optional[GitHubActionsMetadata] = None
    if _is_env_truthy(os.environ.get("GITHUB_ACTIONS")):
        github_meta = GitHubActionsMetadata(
            actor=os.environ.get("GITHUB_ACTOR"),
            actor_id=os.environ.get("GITHUB_ACTOR_ID"),
            repository=os.environ.get("GITHUB_REPOSITORY"),
            repository_id=os.environ.get("GITHUB_REPOSITORY_ID"),
            repository_owner=os.environ.get("GITHUB_REPOSITORY_OWNER"),
            repository_owner_id=os.environ.get("GITHUB_REPOSITORY_OWNER_ID"),
        )

    return CoreUserData(
        device_id=device_id,
        session_id=session_id,
        email=_get_email_sync(),
        app_version=app_version,
        platform=platform,
        user_type=os.environ.get("USER_TYPE"),
        subscription_type=subscription_type,
        rate_limit_tier=rate_limit_tier,
        first_token_time=first_token_time,
        github_actions_metadata=github_meta,
    )


def get_user_for_growth_book() -> CoreUserData:
    """Get user data for GrowthBook (with analytics metadata)."""
    return get_core_user_data(include_analytics_metadata=True)


def _get_platform() -> str:
    """Return a normalised platform string."""
    import platform as _platform
    system = _platform.system().lower()
    mapping = {"darwin": "mac", "windows": "windows", "linux": "linux"}
    return mapping.get(system, system)
