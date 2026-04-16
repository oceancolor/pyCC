"""Datadog analytics stub. Ported from services/analytics/datadog.ts"""
from __future__ import annotations
from typing import Any

async def send_datadog_event(event: str, tags: dict = None, value: float = 1.0) -> None:
    pass
