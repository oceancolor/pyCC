"""Task registry. Ported from tasks.ts"""
from __future__ import annotations
from typing import Any, List, Optional


def get_all_tasks() -> List[Any]:
    """Return all registered task implementations."""
    from claude_code.tasks.local_shell_task import LocalShellTask
    from claude_code.tasks.local_agent_task import LocalAgentTask
    tasks = [LocalShellTask, LocalAgentTask]
    return tasks


def get_task_by_type(task_type: str) -> Optional[Any]:
    for task in get_all_tasks():
        if getattr(task, "type", None) == task_type:
            return task
    return None
