"""Clear command __init__. Re-exports from index.py and submodules."""
from __future__ import annotations

from .index import NAME, DESCRIPTION, ALIASES, TYPE, SUPPORTS_NON_INTERACTIVE
from .clear import call
from .caches import clear_session_caches
from .conversation import clear_conversation

__all__ = [
    "NAME", "DESCRIPTION", "ALIASES", "TYPE", "SUPPORTS_NON_INTERACTIVE",
    "call", "clear_session_caches", "clear_conversation",
]
