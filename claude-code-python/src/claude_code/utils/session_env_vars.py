"""Session-scoped environment variables. Ported from utils/sessionEnvVars.ts"""
from __future__ import annotations
from typing import Dict, Mapping

# Session-scoped env vars set via /env.
# Applied only to spawned child processes, not to the current process itself.
_session_env_vars: Dict[str, str] = {}


def get_session_env_vars() -> Mapping[str, str]:
    """Return a read-only view of the current session environment variables."""
    return _session_env_vars


def set_session_env_var(name: str, value: str) -> None:
    """Set a session-scoped environment variable."""
    _session_env_vars[name] = value


def delete_session_env_var(name: str) -> None:
    """Remove a session-scoped environment variable (no-op if absent)."""
    _session_env_vars.pop(name, None)


def clear_session_env_vars() -> None:
    """Remove all session-scoped environment variables."""
    _session_env_vars.clear()
