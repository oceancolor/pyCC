"""User-Agent string helpers. Ported from userAgent.ts.

Kept dependency-free so SDK-bundled code (bridge, cli/transports) can
import without pulling in auth.py and its transitive dependency tree.
"""
from __future__ import annotations

import platform
import sys
from typing import Optional

__all__ = [
    "get_claude_code_user_agent",
    "get_full_user_agent",
    "get_platform_info",
]


def _get_version() -> str:
    """Return the installed claude-code package version."""
    try:
        from claude_code import __version__

        return __version__
    except Exception:
        return "0.0.0"


def get_claude_code_user_agent() -> str:
    """Return the base claude-code User-Agent string.

    Format: ``claude-code/<version>``
    """
    return f"claude-code/{_get_version()}"


def get_platform_info() -> str:
    """Return a compact platform identifier suitable for User-Agent headers.

    Format: ``python/<py_version> (<os> <arch>)``
    """
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    os_name = platform.system().lower()
    machine = platform.machine().lower()
    return f"python/{py_ver} ({os_name} {machine})"


def get_full_user_agent(extra: Optional[str] = None) -> str:
    """Return a full User-Agent string including platform info.

    Format: ``claude-code/<version> python/<py_version> (<os> <arch>) [extra]``
    """
    parts = [get_claude_code_user_agent(), get_platform_info()]
    if extra:
        parts.append(extra.strip())
    return " ".join(parts)
