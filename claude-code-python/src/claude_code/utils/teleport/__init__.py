"""Teleport utilities.

Provides helpers for integrating with Teleport remote development
environments, including listing available environments, selecting one for
a session, and creating git bundles for code transfer.

Ported from: src/utils/teleport/ (TypeScript)

Usage::

    from claude_code.utils.teleport import (
        EnvironmentResource,
        EnvironmentListResponse,
        is_transient_network_error,
    )
"""
from __future__ import annotations

from claude_code.utils.teleport.environments import (
    EnvironmentListResponse,
    EnvironmentResource,
)
from claude_code.utils.teleport.api import is_transient_network_error

__all__ = [
    "EnvironmentResource",
    "EnvironmentListResponse",
    "is_transient_network_error",
]
