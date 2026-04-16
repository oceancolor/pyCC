"""Background task utilities. Ported from utils/background/."""
from __future__ import annotations
import asyncio
from typing import Any, Callable

_tasks = []

def schedule_background(coro) -> None:
    task = asyncio.ensure_future(coro)
    _tasks.append(task)
