"""Compact grouping utilities. Ported from services/compact/grouping.ts"""
from __future__ import annotations
from typing import Any, List, Tuple


def group_messages_for_compact(messages: List[dict]) -> List[List[dict]]:
    """Group messages into segments suitable for compaction."""
    if not messages:
        return []
    return [messages]
