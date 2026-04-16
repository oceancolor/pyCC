"""Task implementation registry (avoids circular import with tasks.py)."""
from __future__ import annotations
from typing import Any, Optional

_TASK_REGISTRY = None


def _build_registry() -> dict:
    reg = {}
    try:
        from claude_code.tasks.local_agent_task.local_agent_task import LocalAgentTask
        reg[LocalAgentTask.type] = LocalAgentTask
    except ImportError:
        pass
    try:
        from claude_code.tasks.dream_task.dream_task import DreamTask
        reg[DreamTask.type] = DreamTask
    except ImportError:
        pass
    try:
        from claude_code.tasks.remote_agent_task.remote_agent_task import RemoteAgentTask
        reg[RemoteAgentTask.type] = RemoteAgentTask
    except ImportError:
        pass
    return reg


def get_task_by_type(task_type: str) -> Optional[Any]:
    global _TASK_REGISTRY
    if _TASK_REGISTRY is None:
        _TASK_REGISTRY = _build_registry()
    return _TASK_REGISTRY.get(task_type)
