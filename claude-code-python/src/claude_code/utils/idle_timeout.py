"""
Idle timeout manager for SDK mode. Ported from idleTimeout.ts
"""
from __future__ import annotations
import asyncio
import os
from typing import Callable, Optional


class IdleTimeoutManager:
    def __init__(self, is_idle: Callable[[], bool]) -> None:
        self._is_idle = is_idle
        raw = os.environ.get("CLAUDE_CODE_EXIT_AFTER_STOP_DELAY")
        self._delay_ms: Optional[int] = None
        if raw:
            try:
                v = int(raw)
                if v > 0:
                    self._delay_ms = v
            except ValueError:
                pass
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self.stop()
        if self._delay_ms is None:
            return
        delay_s = self._delay_ms / 1000.0

        async def _timer() -> None:
            await asyncio.sleep(delay_s)
            if self._is_idle():
                raise SystemExit(0)

        try:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(_timer())
        except RuntimeError:
            pass

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None


def create_idle_timeout_manager(is_idle: Callable[[], bool]) -> IdleTimeoutManager:
    return IdleTimeoutManager(is_idle)
