# 原始 TS: utils/authFileDescriptor.ts
"""Authentication via file-descriptor token injection (CCR / container mode)."""

from __future__ import annotations

import os
from typing import Optional

# ---------------------------------------------------------------------------
# Well-known paths used in CCR (Claude Code Remote) containers.
# The Go environment-manager creates /home/claude/.claude/remote/ and writes
# these files so subprocesses can find tokens without inheriting the FD.
# ---------------------------------------------------------------------------

_CCR_TOKEN_DIR = "/home/claude/.claude/remote"
CCR_OAUTH_TOKEN_PATH = f"{_CCR_TOKEN_DIR}/.oauth_token"
CCR_API_KEY_PATH = f"{_CCR_TOKEN_DIR}/.api_key"
CCR_SESSION_INGRESS_TOKEN_PATH = f"{_CCR_TOKEN_DIR}/.session_ingress_token"


def get_api_key_from_file_descriptor() -> Optional[str]:
    """Read the API key from the well-known CCR path, if available."""
    return _read_token_file(CCR_API_KEY_PATH)


def get_oauth_token_from_file_descriptor() -> Optional[str]:
    """Read the OAuth token from the well-known CCR path, if available."""
    return _read_token_file(CCR_OAUTH_TOKEN_PATH)


def maybe_persist_token_for_subprocesses(
    path: str,
    token: str,
    token_name: str,
) -> None:
    """Best-effort: write *token* to *path* so CCR subprocesses can read it.

    Only runs inside CCR containers (CLAUDE_CODE_REMOTE env var must be set).
    Outside CCR there is no /home/claude/ and no reason to put a token on disk
    that the FD was meant to keep off disk.
    """
    if not _is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE")):
        return

    try:
        os.makedirs(_CCR_TOKEN_DIR, mode=0o700, exist_ok=True)
        with open(path, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
            f.write(token)
    except Exception as exc:
        # Best-effort; log but don't crash
        try:
            from claude_code.utils.log import log_for_debugging  # type: ignore
            log_for_debugging(f"maybe_persist_token_for_subprocesses({token_name}): {exc}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _read_token_file(path: str) -> Optional[str]:
    """Read the first line of a token file, stripping whitespace."""
    try:
        with open(path) as f:
            content = f.read().strip()
            return content if content else None
    except (FileNotFoundError, PermissionError):
        return None


def _is_env_truthy(value: Optional[str]) -> bool:
    """Return True when *value* is a non-empty, non-false string."""
    if not value:
        return False
    return value.lower() not in {"0", "false", "no", "off"}
