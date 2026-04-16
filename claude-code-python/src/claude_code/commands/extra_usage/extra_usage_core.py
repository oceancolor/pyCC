"""Extra usage core logic. Stub. Ported from commands/extra-usage/extra-usage-core.ts (118L)."""
from __future__ import annotations
from typing import Any, Optional

async def get_extra_usage(session_id: Optional[str] = None) -> dict:
    """Return extra/extended usage metrics."""
    return {"total_tokens": 0, "total_cost": 0.0}
