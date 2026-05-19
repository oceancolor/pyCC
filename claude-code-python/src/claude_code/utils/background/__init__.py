"""Background task utilities.

Provides helpers for scheduling and executing fire-and-forget background
tasks (e.g. telemetry flushes, cache writes) without blocking the main
async event loop.

Ported from: src/utils/background/ (TypeScript)

Usage::

    from claude_code.utils.background import schedule_background, run_background_tasks_sync
"""
from __future__ import annotations

from claude_code.utils.background.background import (
    run_background_tasks_sync,
    schedule_background,
)

__all__ = [
    "schedule_background",
    "run_background_tasks_sync",
]
