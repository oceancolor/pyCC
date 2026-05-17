"""RemoteAgentTask package. Ported from tasks/RemoteAgentTask/."""
from __future__ import annotations

from .remote_agent_task import (
    RemoteAgentTask,
    RemoteAgentTaskState,
    ReviewProgress,
    REMOTE_TASK_TYPES,
    RemoteTaskType,
    is_remote_task_type,
    is_remote_agent_task,
    register_completion_checker,
)

__all__ = [
    "RemoteAgentTask",
    "RemoteAgentTaskState",
    "ReviewProgress",
    "REMOTE_TASK_TYPES",
    "RemoteTaskType",
    "is_remote_task_type",
    "is_remote_agent_task",
    "register_completion_checker",
]
