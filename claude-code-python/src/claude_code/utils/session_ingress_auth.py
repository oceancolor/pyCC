"""
Session ingress authentication utilities.

Provides helpers for obtaining and using the session ingress token
that authenticates WebSocket / API requests from CCR bridge processes.

Priority order for token resolution:
  1. CLAUDE_CODE_SESSION_ACCESS_TOKEN env var
  2. File descriptor CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR
  3. Well-known file CLAUDE_SESSION_INGRESS_TOKEN_FILE (or default path)
"""

import os
import platform
from typing import Optional

# Default well-known file path (mirrors TS CCR_SESSION_INGRESS_TOKEN_PATH)
_CCR_SESSION_INGRESS_TOKEN_PATH = os.path.expanduser(
    "~/.claude/remote/.session_ingress_token"
)

# Module-level cache: None = not yet attempted, empty string = no token found
_cached_token: Optional[str] = None  # sentinel: use _token_read flag
_token_read: bool = False


def _read_token_from_file(path: str) -> Optional[str]:
    """Read token from a well-known file path. Returns None on any error."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            token = fh.read().strip()
            return token or None
    except OSError:
        return None


def _get_token_from_fd() -> Optional[str]:
    """Read token from a file descriptor env var, with well-known-file fallback."""
    global _cached_token, _token_read

    if _token_read:
        return _cached_token

    fd_env = os.environ.get("CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR")
    if not fd_env:
        # No FD – try well-known file
        path = os.environ.get(
            "CLAUDE_SESSION_INGRESS_TOKEN_FILE", _CCR_SESSION_INGRESS_TOKEN_PATH
        )
        token = _read_token_from_file(path)
        _cached_token = token
        _token_read = True
        return token

    try:
        fd = int(fd_env)
    except ValueError:
        _cached_token = None
        _token_read = True
        return None

    # Build fd path (platform-specific)
    system = platform.system()
    if system == "Darwin":
        fd_path = f"/dev/fd/{fd}"
    else:
        fd_path = f"/proc/self/fd/{fd}"

    try:
        with open(fd_path, "r", encoding="utf-8") as fh:
            token = fh.read().strip()
        if not token:
            _cached_token = None
            _token_read = True
            return None
        _cached_token = token
        _token_read = True
        return token
    except OSError:
        # FD unreadable (e.g. subprocess) – fall back to well-known file
        path = os.environ.get(
            "CLAUDE_SESSION_INGRESS_TOKEN_FILE", _CCR_SESSION_INGRESS_TOKEN_PATH
        )
        token = _read_token_from_file(path)
        _cached_token = token
        _token_read = True
        return token


def get_session_ingress_auth_token() -> Optional[str]:
    """
    Return the session ingress token or None if unavailable.

    Priority:
      1. CLAUDE_CODE_SESSION_ACCESS_TOKEN env var
      2. File descriptor / well-known file (cached)
    """
    env_token = os.environ.get("CLAUDE_CODE_SESSION_ACCESS_TOKEN")
    if env_token:
        return env_token
    return _get_token_from_fd()


def get_session_ingress_auth_headers() -> dict[str, str]:
    """
    Build auth headers for the current session token.

    - sk-ant-sid tokens → Cookie: sessionKey=<token> (+ X-Organization-Uuid)
    - JWT tokens → Authorization: Bearer <token>
    """
    token = get_session_ingress_auth_token()
    if not token:
        return {}
    if token.startswith("sk-ant-sid"):
        headers: dict[str, str] = {"Cookie": f"sessionKey={token}"}
        org_uuid = os.environ.get("CLAUDE_CODE_ORGANIZATION_UUID")
        if org_uuid:
            headers["X-Organization-Uuid"] = org_uuid
        return headers
    return {"Authorization": f"Bearer {token}"}


def update_session_ingress_auth_token(token: str) -> None:
    """
    Update the in-process session token by setting the env var.
    Mirrors TS updateSessionIngressAuthToken.
    """
    os.environ["CLAUDE_CODE_SESSION_ACCESS_TOKEN"] = token


def reset_token_cache() -> None:
    """Reset the cached token (for testing)."""
    global _cached_token, _token_read
    _cached_token = None
    _token_read = False
