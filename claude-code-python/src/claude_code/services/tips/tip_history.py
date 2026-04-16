"""Tip display history. Stub."""
from __future__ import annotations
import os, json
_shown: set = set()
def has_seen_tip(tip_id: str) -> bool: return tip_id in _shown
def mark_tip_seen(tip_id: str) -> None: _shown.add(tip_id)
