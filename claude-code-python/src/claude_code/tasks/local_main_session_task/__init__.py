"""LocalMainSessionTask package.

Handles the lifecycle of the main session query task when it runs in the
background — registering it with the task framework, completing it, and
foregrounding it when the user re-enters the session.

Ported from: src/tasks/localMainSessionTask/ (TypeScript)

Usage::

    from claude_code.tasks.local_main_session_task import (
        LocalMainSessionTaskState,
        register_main_session_task,
        complete_main_session_task,
        foreground_main_session_task,
        start_background_session,
        is_main_session_task,
    )
"""
from __future__ import annotations

from .local_main_session_task import (
    LocalMainSessionTaskState,
    register_main_session_task,
    complete_main_session_task,
    foreground_main_session_task,
    start_background_session,
    is_main_session_task,
)

__all__ = [
    "LocalMainSessionTaskState",
    "register_main_session_task",
    "complete_main_session_task",
    "foreground_main_session_task",
    "start_background_session",
    "is_main_session_task",
]
