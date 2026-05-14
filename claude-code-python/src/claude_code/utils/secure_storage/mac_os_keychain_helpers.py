"""macOS Keychain helper utilities. Ported from utils/secureStorage/macOsKeychainHelpers.ts"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Optional, Dict, Any

SecureStorageData = Dict[str, Any]

# Suffix distinguishing OAuth credentials from legacy API-key entry.
# DO NOT change – it's part of the keychain lookup key.
CREDENTIALS_SERVICE_SUFFIX = "-credentials"

# Cache TTL: 30 seconds
KEYCHAIN_CACHE_TTL_MS = 30_000


class _KeychainCacheState:
    """Mutable cache state shared between this module and macOsKeychainStorage."""

    def __init__(self) -> None:
        self.cache: dict = {"data": None, "cached_at": 0}  # cached_at=0 means invalid
        self.generation: int = 0
        self.read_in_flight: Optional[object] = None


keychain_cache_state = _KeychainCacheState()


def clear_keychain_cache() -> None:
    """Invalidate the keychain cache and increment the generation counter."""
    keychain_cache_state.cache = {"data": None, "cached_at": 0}
    keychain_cache_state.generation += 1
    keychain_cache_state.read_in_flight = None


def prime_keychain_cache_from_prefetch(stdout: Optional[str]) -> None:
    """Prime the keychain cache from a prefetch result.

    Only writes if the cache hasn't been touched yet (cached_at == 0).
    """
    import json

    if keychain_cache_state.cache["cached_at"] != 0:
        return

    data: Optional[SecureStorageData] = None
    if stdout:
        try:
            data = json.loads(stdout)
        except Exception:
            return  # Malformed prefetch – let sync read() re-fetch

    keychain_cache_state.cache = {"data": data, "cached_at": int(time.time() * 1000)}


def get_mac_os_keychain_storage_service_name(service_suffix: str = "") -> str:
    """Build the keychain service name for the current config directory.

    Uses a hash suffix for non-default config directories so multiple
    Claude Code installations don't share the same keychain entry.
    """
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir

        config_dir = get_claude_config_home_dir()
    except Exception:
        config_dir = os.path.expanduser("~/.claude")

    is_default_dir = not os.environ.get("CLAUDE_CONFIG_DIR")

    if is_default_dir:
        dir_hash = ""
    else:
        dir_hash = (
            "-" + hashlib.sha256(config_dir.encode()).hexdigest()[:8]
        )

    # Equivalent of getOauthConfig().OAUTH_FILE_SUFFIX – default is empty string
    oauth_suffix = os.environ.get("CLAUDE_OAUTH_FILE_SUFFIX", "")
    return f"Claude Code{oauth_suffix}{service_suffix}{dir_hash}"


def get_username() -> str:
    """Return the current username, with a safe fallback."""
    try:
        username = os.environ.get("USER")
        if username:
            return username
        import pwd

        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return "claude-code-user"
