# 原始 TS: utils/abortController.ts
"""AbortController 封装（asyncio.Event 实现）"""
from __future__ import annotations
import asyncio
from typing import Optional


class AbortController:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def abort(self) -> None:
        self._event.set()

    @property
    def signal(self) -> asyncio.Event:
        return self._event

    @property
    def is_aborted(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()


def create_abort_controller() -> AbortController:
    return AbortController()
