"""Tips service stub. Ported from services/tips."""
from __future__ import annotations
from typing import Optional

async def get_tip_of_the_day() -> Optional[str]:
    return None

async def mark_tip_seen(tip_id: str) -> None:
    pass
