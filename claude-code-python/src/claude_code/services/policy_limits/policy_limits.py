"""Policy limits service stub. Ported from services/policyLimits."""
from __future__ import annotations
from typing import Optional

async def get_policy_limits() -> dict:
    return {}

def is_over_policy_limit(metric: str, value: float) -> bool:
    return False
