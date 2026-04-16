"""Session cache clearing utilities. Ported from commands/clear/caches.ts"""
from __future__ import annotations
from typing import FrozenSet

def clear_session_caches(preserved_agent_ids: FrozenSet[str] = frozenset()) -> None:
    """Clear all session-related caches."""
    pass
