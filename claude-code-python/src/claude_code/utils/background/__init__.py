"""Background task utilities sub-package. Ported from utils/background/."""
from __future__ import annotations

from claude_code.utils.background.background import (
    run_background_tasks_sync,
    schedule_background,
)

__all__ = [
    "schedule_background",
    "run_background_tasks_sync",
]
