"""Consolidation lock utilities. Ported from services/autoDream/consolidationLock.ts"""
from __future__ import annotations
import asyncio, os, time
from typing import List, Optional

async def read_last_consolidated_at() -> float:
    return 0.0

async def list_sessions_touched_since(since_ts: float) -> List[str]:
    return []

async def try_acquire_consolidation_lock() -> Optional[float]:
    return None

async def rollback_consolidation_lock(prior_mtime: Optional[float]) -> None:
    pass
