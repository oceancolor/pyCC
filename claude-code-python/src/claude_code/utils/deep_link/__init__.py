"""Deep link utilities sub-package. Ported from utils/deepLink/.

Provides helpers for registering and parsing claude-cli:// deep links used
to open Claude Code from the browser and other applications.
"""
from __future__ import annotations

from claude_code.utils.deep_link.parse_deep_link import (
    DEEP_LINK_PROTOCOL,
    DeepLinkAction,
)

__all__ = [
    "DEEP_LINK_PROTOCOL",
    "DeepLinkAction",
]
