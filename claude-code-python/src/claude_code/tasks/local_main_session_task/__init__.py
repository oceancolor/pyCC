"""LocalMainSessionTask - handles backgrounding the main session query."""

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
