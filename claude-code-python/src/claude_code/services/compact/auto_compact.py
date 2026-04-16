"""AutoCompact service stub. Ported from services/compact/autoCompact.ts"""
from __future__ import annotations
from typing import Any

async def should_auto_compact(context: Any) -> bool:
    return False

async def run_auto_compact(context: Any) -> None:
    pass
