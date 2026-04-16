"""
XDG Base Directory utilities - Python port of xdg.ts

Implements the XDG Base Directory specification for organizing components
across appropriate system directories.

See: https://specifications.freedesktop.org/basedir-spec/latest/

Provides:
- get_xdg_state_home(env, homedir)  → ~/.local/state  (or XDG_STATE_HOME)
- get_xdg_cache_home(env, homedir)  → ~/.cache         (or XDG_CACHE_HOME)
- get_xdg_data_home(env, homedir)   → ~/.local/share   (or XDG_DATA_HOME)
- get_user_bin_dir(homedir)         → ~/.local/bin
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _resolve(
    env: Optional[Dict[str, Optional[str]]],
    homedir: Optional[str],
) -> tuple[Dict[str, Optional[str]], str]:
    """Return (env_dict, home_str)."""
    resolved_env: Dict[str, Optional[str]] = env if env is not None else dict(os.environ)
    resolved_home = homedir or os.environ.get("HOME") or str(Path.home())
    return resolved_env, resolved_home


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_xdg_state_home(
    env: Optional[Dict[str, Optional[str]]] = None,
    homedir: Optional[str] = None,
) -> str:
    """XDG state directory. Default: ~/.local/state"""
    e, home = _resolve(env, homedir)
    return str(e.get("XDG_STATE_HOME") or Path(home) / ".local" / "state")


def get_xdg_cache_home(
    env: Optional[Dict[str, Optional[str]]] = None,
    homedir: Optional[str] = None,
) -> str:
    """XDG cache directory. Default: ~/.cache"""
    e, home = _resolve(env, homedir)
    return str(e.get("XDG_CACHE_HOME") or Path(home) / ".cache")


def get_xdg_data_home(
    env: Optional[Dict[str, Optional[str]]] = None,
    homedir: Optional[str] = None,
) -> str:
    """XDG data directory. Default: ~/.local/share"""
    e, home = _resolve(env, homedir)
    return str(e.get("XDG_DATA_HOME") or Path(home) / ".local" / "share")


def get_user_bin_dir(
    env: Optional[Dict[str, Optional[str]]] = None,
    homedir: Optional[str] = None,
) -> str:
    """User bin directory. Default: ~/.local/bin (not strictly XDG but follows convention)."""
    _, home = _resolve(env, homedir)
    return str(Path(home) / ".local" / "bin")


# ---------------------------------------------------------------------------
# Convenience aliases used by other modules
# ---------------------------------------------------------------------------

def get_xdg_data_dir() -> str:
    """Alias for get_xdg_data_home() with no overrides."""
    return get_xdg_data_home()


def get_xdg_config_dir() -> str:
    """XDG config home. Default: ~/.config (or XDG_CONFIG_HOME)."""
    raw = os.environ.get("XDG_CONFIG_HOME")
    if raw:
        return raw
    return str(Path.home() / ".config")
