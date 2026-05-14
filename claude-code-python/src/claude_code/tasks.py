"""Task registry. Ported from tasks.ts"""
from __future__ import annotations
import os
from typing import Any, List, Optional


def get_all_tasks() -> List[Any]:
    """Return all registered task implementations.

    Mirrors getAllTasks() from tasks.ts.
    Feature-gated tasks are included only if the matching env flag is set.
    """
    from claude_code.tasks.local_shell_task import LocalShellTask
    from claude_code.tasks.local_agent_task import LocalAgentTask
    from claude_code.tasks.remote_agent_task import RemoteAgentTask
    from claude_code.tasks.dream_task import DreamTask

    tasks: List[Any] = [LocalShellTask, LocalAgentTask, RemoteAgentTask, DreamTask]

    # Feature-gated tasks
    if os.environ.get("FEATURE_WORKFLOW_SCRIPTS", "").lower() in ("1", "true"):
        try:
            from claude_code.tasks.local_workflow_task import LocalWorkflowTask  # type: ignore
            tasks.append(LocalWorkflowTask)
        except ImportError:
            pass

    if os.environ.get("FEATURE_MONITOR_TOOL", "").lower() in ("1", "true"):
        try:
            from claude_code.tasks.monitor_mcp_task import MonitorMcpTask  # type: ignore
            tasks.append(MonitorMcpTask)
        except ImportError:
            pass

    return tasks


def get_task_by_type(task_type: str) -> Optional[Any]:
    """Return the task class matching *task_type*, or None if not found."""
    for task in get_all_tasks():
        if getattr(task, "type", None) == task_type:
            return task
    return None
