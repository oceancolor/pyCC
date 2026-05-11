"""
commands/logout.py — top-level /logout command shim.

Ported from: commands/logout/logout.tsx

Delegates to the ``commands/logout/`` package which holds the full
implementation (perform_logout, clear_auth_related_caches, call).
"""
from __future__ import annotations

from claude_code.commands.logout.index import (  # noqa: F401
    call,
    perform_logout,
    _clear_auth_related_caches as clear_auth_related_caches,
)

__all__ = ["call", "perform_logout", "clear_auth_related_caches"]
