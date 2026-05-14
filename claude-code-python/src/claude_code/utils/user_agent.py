"""User-Agent string helpers. Ported from utils/userAgent.ts

Kept dependency-free so SDK-bundled code (bridge, cli/transports) can
import without pulling in auth.ts and its transitive dependency tree.
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Optional

try:
    from claude_code import __version__ as _VERSION
except ImportError:
    _VERSION = "0.0.0"


def get_claude_code_user_agent() -> str:
    """Return the canonical ``User-Agent`` header value for Claude Code.

    Format: ``claude-code/<version>``
    """
    return f"claude-code/{_VERSION}"


def get_full_user_agent(extra: Optional[str] = None) -> str:
    """Return an extended User-Agent that includes runtime info.

    Format: ``claude-code/<version> Python/<py-version> <platform>``
    Optionally appends *extra* (e.g. ``"webrtc"``).
    """
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    plat = _platform_tag()
    base = f"claude-code/{_VERSION} Python/{py_version} {plat}"
    if extra:
        base += f" {extra}"
    return base


def _platform_tag() -> str:
    """Return a short platform identifier string."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    return f"{system}/{machine}"


def get_environment_user_agent_suffix() -> str:
    """Return an optional extra suffix sourced from an environment variable.

    The environment variable ``CLAUDE_CODE_USER_AGENT_SUFFIX`` lets
    integration environments (e.g. CI, IDE plugins) append their own
    identifier without modifying core code.
    """
    return os.environ.get("CLAUDE_CODE_USER_AGENT_SUFFIX", "")
