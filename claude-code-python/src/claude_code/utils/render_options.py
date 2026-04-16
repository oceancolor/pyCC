"""
Render options: TTY stdin override for Ink/TUI rendering.
Ported from renderOptions.ts (UI-agnostic subset only).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional


def _is_env_truthy(value: Optional[str]) -> bool:
    """Return True if env var value looks truthy."""
    return value is not None and value.lower() in ("1", "true", "yes", "on")


@dataclass
class RenderOptions:
    """Base render options (Python TUI equivalent of Ink's RenderOptions)."""
    exit_on_ctrl_c: bool = False
    use_tty: bool = False
    tty_path: str = "/dev/tty"


_cached_tty_available: Optional[bool] = None


def is_tty_available() -> bool:
    """Check if /dev/tty is available for interactive rendering."""
    global _cached_tty_available
    if _cached_tty_available is not None:
        return _cached_tty_available

    # Already a TTY — no override needed
    if sys.stdin.isatty():
        _cached_tty_available = False
        return False

    # Skip in CI
    if _is_env_truthy(os.environ.get("CI")):
        _cached_tty_available = False
        return False

    # Skip on Windows
    if sys.platform == "win32":
        _cached_tty_available = False
        return False

    # Try opening /dev/tty
    try:
        fd = os.open("/dev/tty", os.O_RDONLY)
        os.close(fd)
        _cached_tty_available = True
        return True
    except OSError:
        _cached_tty_available = False
        return False


def get_base_render_options(exit_on_ctrl_c: bool = False) -> RenderOptions:
    """
    Return base render options, enabling TTY override when stdin is piped.
    Use this for all TUI render() calls.
    """
    use_tty = is_tty_available()
    return RenderOptions(exit_on_ctrl_c=exit_on_ctrl_c, use_tty=use_tty)


def reset_tty_cache() -> None:
    """Reset TTY availability cache (for testing)."""
    global _cached_tty_available
    _cached_tty_available = None
