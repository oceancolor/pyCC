"""Deep-link utilities.

Provides helpers for registering and parsing ``claude-cli://`` deep links,
which are used to open Claude Code from browser extensions, IDEs, and other
external applications.

Ported from: src/utils/deepLink/ (TypeScript)

Usage::

    from claude_code.utils.deep_link import DEEP_LINK_PROTOCOL, DeepLinkAction
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
