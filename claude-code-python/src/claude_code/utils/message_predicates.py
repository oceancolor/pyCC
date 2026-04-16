"""Message type predicates. Ported from messagePredicates.ts"""
from __future__ import annotations
from typing import Any

def is_human_turn(m: Any) -> bool:
    return (getattr(m, 'type', None) == 'user' and
            not getattr(m, 'is_meta', False) and
            getattr(m, 'tool_use_result', None) is None)
