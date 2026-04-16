"""Analytics sink stub. Ported from services/analytics/sink.ts"""
from __future__ import annotations
from typing import Any

class AnalyticsSink:
    async def record(self, event: str, payload: Any = None) -> None:
        pass

    async def flush(self) -> None:
        pass
