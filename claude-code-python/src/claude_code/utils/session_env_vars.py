"""Session-scoped environment variables. Ported from sessionEnvVars.ts.

Environment variables set via the /env slash command.  Applied only to
spawned child processes (via bash provider env overrides), not to the
current REPL process itself.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterator, Mapping, Optional, Tuple

__all__ = [
    "get_session_env_vars",
    "set_session_env_var",
    "delete_session_env_var",
    "clear_session_env_vars",
    "apply_to_environ",
    "list_session_env_vars",
    "validate_env_var_name",
]

# Module-level store — intentionally module-scoped so the CLI's setup() and
# the test suite can both reset it without passing objects around.
_session_env_vars: Dict[str, str] = {}

_VALID_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_env_var_name(name: str) -> bool:
    """Return True if *name* is a valid POSIX environment variable name."""
    return bool(_VALID_NAME_RE.match(name))


def get_session_env_vars() -> Mapping[str, str]:
    """Return a read-only view of the current session environment variables."""
    return _session_env_vars


def set_session_env_var(name: str, value: str) -> None:
    """Set a session-scoped environment variable.

    Raises ValueError if *name* is not a valid identifier.
    """
    if not validate_env_var_name(name):
        raise ValueError(f"Invalid environment variable name: {name!r}")
    _session_env_vars[name] = value


def delete_session_env_var(name: str) -> None:
    """Remove a session-scoped environment variable (no-op if absent)."""
    _session_env_vars.pop(name, None)


def clear_session_env_vars() -> None:
    """Remove all session-scoped environment variables."""
    _session_env_vars.clear()


def apply_to_environ(base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return a copy of *base* (or os.environ) with session vars merged in.

    Session vars take precedence over existing values in *base*.
    """
    result = dict(base if base is not None else os.environ)
    result.update(_session_env_vars)
    return result


def list_session_env_vars() -> Iterator[Tuple[str, str]]:
    """Iterate over (name, value) pairs of all session env vars."""
    return iter(_session_env_vars.items())
