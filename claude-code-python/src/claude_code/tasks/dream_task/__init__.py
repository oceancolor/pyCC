"""DreamTask package. Ported from tasks/DreamTask/."""
from __future__ import annotations

from .dream_task import (
    DreamTask,
    DreamTaskState,
    DreamTurn,
    DreamPhase,
    is_dream_task,
    register_dream_task,
    add_dream_turn,
    complete_dream_task,
    fail_dream_task,
    MAX_TURNS,
)

__all__ = [
    "DreamTask",
    "DreamTaskState",
    "DreamTurn",
    "DreamPhase",
    "is_dream_task",
    "register_dream_task",
    "add_dream_turn",
    "complete_dream_task",
    "fail_dream_task",
    "MAX_TURNS",
]
