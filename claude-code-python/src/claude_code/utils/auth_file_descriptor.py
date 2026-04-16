"""
Auth file descriptor utilities for Claude Code Remote (CCR).

Handles reading credentials from Unix file descriptors and well-known
fallback files in the CCR container environment.

Well-known token file locations:
- /home/claude/.claude/remote/.oauth_token
- /home/claude/.claude/remote/.api_key
- /home/claude/.claude/remote/.session_ingress_token
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CCR_TOKEN_DIR = "/home/claude/.claude/remote"
CCR_OAUTH_TOKEN_PATH = f"{CCR_TOKEN_DIR}/.oauth_token"
CCR_API_KEY_PATH = f"{CCR_TOKEN_DIR}/.api_key"
CCR_SESSION_INGRESS_TOKEN_PATH = f"{CCR_TOKEN_DIR}/.session_ingress_token"

# ---------------------------------------------------------------------------
# Module-level credential cache (mirrors TS global state)
# ---------------------------------------------------------------------------

_cached_oauth_token: Optional[str] = None   # type: ignore[assignment]
_oauth_token_fetched: bool = False
_cached_api_key: Optional[str] = None       # type: ignore[assignment]
_api_key_fetched: bool = False


def _is_env_truthy(value: Optional[str]) -> bool:
    return bool(value and value.lower() not in ("0", "false", "no", ""))


# ---------------------------------------------------------------------------
# Well-known file helpers
# ---------------------------------------------------------------------------

def maybe_persist_token_for_subprocesses(
    path: str, token: str, token_name: str
) -> None:
    """
    Best-effort write of token to a well-known location for subprocess access.
    CCR-gated: outside CCR there is no /home/claude/ and no reason to put a
    token on disk.
    """
    if not _is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE")):
        return
    try:
        token_dir = Path(CCR_TOKEN_DIR)
        token_dir.mkdir(parents=True, exist_ok=True)
        token_dir.chmod(0o700)
        p = Path(path)
        p.write_text(token, encoding="utf-8")
        p.chmod(0o600)
    except Exception:
        pass


def read_token_from_well_known_file(path: str, token_name: str) -> Optional[str]:
    """
    Fallback read from a well-known file.
    ENOENT is the expected outcome outside CCR — treated as "no fallback".
    """
    try:
        token = Path(path).read_text(encoding="utf-8").strip()
        return token if token else None
    except FileNotFoundError:
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core FD-or-file credential reader
# ---------------------------------------------------------------------------

def _get_credential_from_fd(
    *,
    env_var: str,
    well_known_path: str,
    label: str,
    cached: Optional[str],
    fetched: bool,
    set_cached_fn: "callable",  # type: ignore[type-arg]
) -> Optional[str]:
    """
    Shared FD-or-well-known-file credential reader.

    Priority order:
    1. File descriptor — env var points at a pipe FD passed by the Go env-manager.
       Pipe is drained on first read and doesn't cross exec/tmux boundaries.
    2. Well-known file — written by this function on successful FD read.
       Covers subprocesses that can't inherit the FD.
    """
    if fetched:
        return cached

    fd_env = os.environ.get(env_var)
    if not fd_env:
        # No FD env var — try the well-known file
        from_file = read_token_from_well_known_file(well_known_path, label)
        set_cached_fn(from_file)
        return from_file

    try:
        fd = int(fd_env)
    except ValueError:
        set_cached_fn(None)
        return None

    try:
        # Use /proc/self/fd on Linux, /dev/fd on macOS/BSD
        import platform
        system = platform.system().lower()
        if system in ("darwin", "freebsd"):
            fd_path = f"/dev/fd/{fd}"
        else:
            fd_path = f"/proc/self/fd/{fd}"

        with open(fd_path, "r", encoding="utf-8") as f:
            token = f.read().strip()

        if not token:
            set_cached_fn(None)
            return None

        set_cached_fn(token)
        maybe_persist_token_for_subprocesses(well_known_path, token, label)
        return token

    except Exception:
        # FD read failed (e.g., ENXIO in subprocess) — try well-known file
        from_file = read_token_from_well_known_file(well_known_path, label)
        set_cached_fn(from_file)
        return from_file


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_oauth_token_from_file_descriptor() -> Optional[str]:
    """
    Get the CCR-injected OAuth token.
    Env var: CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR
    Well-known file: /home/claude/.claude/remote/.oauth_token
    """
    global _cached_oauth_token, _oauth_token_fetched

    def _set(value: Optional[str]) -> None:
        global _cached_oauth_token, _oauth_token_fetched
        _cached_oauth_token = value
        _oauth_token_fetched = True

    return _get_credential_from_fd(
        env_var="CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
        well_known_path=CCR_OAUTH_TOKEN_PATH,
        label="OAuth token",
        cached=_cached_oauth_token,
        fetched=_oauth_token_fetched,
        set_cached_fn=_set,
    )


def get_api_key_from_file_descriptor() -> Optional[str]:
    """
    Get the CCR-injected API key.
    Env var: CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR
    Well-known file: /home/claude/.claude/remote/.api_key
    """
    global _cached_api_key, _api_key_fetched

    def _set(value: Optional[str]) -> None:
        global _cached_api_key, _api_key_fetched
        _cached_api_key = value
        _api_key_fetched = True

    return _get_credential_from_fd(
        env_var="CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
        well_known_path=CCR_API_KEY_PATH,
        label="API key",
        cached=_cached_api_key,
        fetched=_api_key_fetched,
        set_cached_fn=_set,
    )


def reset_credential_cache() -> None:
    """Reset all credential caches (e.g., for testing)."""
    global _cached_oauth_token, _oauth_token_fetched
    global _cached_api_key, _api_key_fetched
    _cached_oauth_token = None
    _oauth_token_fetched = False
    _cached_api_key = None
    _api_key_fetched = False
