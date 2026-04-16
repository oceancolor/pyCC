"""Analytics index. Ported from services/analytics/index.ts"""
from __future__ import annotations
from typing import Any

def log_event(event_name: str, payload: Any = None) -> None:
    """Log an analytics event. Stub: no-op."""
    pass

async def flush_analytics() -> None:
    """Flush buffered analytics events. Stub."""
    pass
