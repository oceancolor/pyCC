"""Analytics sink killswitch. Ported from services/analytics/sinkKillswitch.ts"""
from __future__ import annotations
import os

def is_analytics_enabled() -> bool:
    return os.environ.get("CLAUDE_CODE_DISABLE_ANALYTICS", "").lower() not in ("1", "true")
