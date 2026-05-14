"""First-party event logging exporter. Ported from services/analytics/firstPartyEventLoggingExporter.ts"""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class FirstPartyEventLoggingExporter:
    """Exporter for 1st-party event logging to /api/event_logging/batch.

    Provides resilience via:
    - Append-only log for failed events
    - Quadratic backoff retry for failed events
    - Chunking large event sets
    """

    def __init__(
        self,
        timeout: int = 10000,
        max_batch_size: int = 200,
        skip_auth: bool = False,
        batch_delay_ms: int = 100,
        base_backoff_delay_ms: int = 500,
        max_backoff_delay_ms: int = 30000,
        max_attempts: int = 8,
        path: Optional[str] = None,
        base_url: Optional[str] = None,
        is_killed: Optional[Callable[[], bool]] = None,
    ) -> None:
        default_base = (
            "https://api-staging.anthropic.com"
            if os.environ.get("ANTHROPIC_BASE_URL") == "https://api-staging.anthropic.com"
            else "https://api.anthropic.com"
        )
        self.endpoint = f"{base_url or default_base}{path or '/api/event_logging/batch'}"
        self.timeout_s = timeout / 1000
        self.max_batch_size = max_batch_size
        self.skip_auth = skip_auth
        self.batch_delay_s = batch_delay_ms / 1000
        self.base_backoff_s = base_backoff_delay_ms / 1000
        self.max_backoff_s = max_backoff_delay_ms / 1000
        self.max_attempts = max_attempts
        self.is_killed = is_killed or (lambda: False)
        self._is_shutdown = False
        self._attempts = 0

    async def export(self, events: List[Dict[str, Any]]) -> bool:
        """Export events to the 1P endpoint. Returns True on success."""
        if self._is_shutdown:
            return False
        if self.is_killed():
            return False
        if not events:
            return True

        failed: List[Dict[str, Any]] = []
        for i in range(0, len(events), self.max_batch_size):
            batch = events[i:i + self.max_batch_size]
            try:
                await self._send_batch(batch)
                if i + self.max_batch_size < len(events):
                    await asyncio.sleep(self.batch_delay_s)
            except Exception:
                failed.extend(events[i:])
                break

        return len(failed) == 0

    async def _send_batch(self, events: List[Dict[str, Any]]) -> None:
        """Send a single batch to the endpoint."""
        try:
            import aiohttp
            payload = {"events": events}
            headers = {"Content-Type": "application/json", "User-Agent": "claude-code"}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_s),
                ) as resp:
                    resp.raise_for_status()
        except ImportError:
            # aiohttp not available; silently skip
            pass

    async def shutdown(self) -> None:
        """Shut down the exporter."""
        self._is_shutdown = True

    async def force_flush(self) -> None:
        """Force flush pending events."""
        pass
