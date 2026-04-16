"""Task types and factories. Ported from Task.ts"""
from __future__ import annotations
import os
import secrets
from typing import Any, Callable, Dict, Literal, Optional, TypedDict

TaskType = Literal[
    "local_bash", "local_agent", "remote_agent",
    "in_process_teammate", "local_workflow", "monitor_mcp", "dream"
]

TaskStatus = Literal["pending", "running", "completed", "failed", "killed"]


def is_terminal_task_status(status: TaskStatus) -> bool:
    return status in ("completed", "failed", "killed")


TASK_ID_PREFIXES = {
    "local_bash": "b",
    "local_agent": "a",
    "remote_agent": "r",
    "in_process_teammate": "t",
    "local_workflow": "w",
    "monitor_mcp": "m",
    "dream": "d",
}

TASK_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def generate_task_id(task_type: TaskType) -> str:
    prefix = TASK_ID_PREFIXES.get(task_type, "x")
    rand = secrets.token_bytes(8)
    suffix = "".join(TASK_ID_ALPHABET[b % len(TASK_ID_ALPHABET)] for b in rand)
    return prefix + suffix


def get_task_output_path(task_id: str) -> str:
    output_dir = os.path.join(os.path.expanduser("~"), ".claude", "task-outputs")
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{task_id}.txt")


class TaskStateBase(TypedDict, total=False):
    id: str
    type: str
    status: str
    description: str
    tool_use_id: Optional[str]
    start_time: float
    end_time: Optional[float]
    total_paused_ms: Optional[float]
    output_file: str
    output_offset: int
    notified: bool


def create_task_state_base(
    task_id: str,
    task_type: TaskType,
    description: str,
    tool_use_id: Optional[str] = None,
) -> TaskStateBase:
    import time
    return {
        "id": task_id,
        "type": task_type,
        "status": "pending",
        "description": description,
        "tool_use_id": tool_use_id,
        "start_time": time.time() * 1000,
        "output_file": get_task_output_path(task_id),
        "output_offset": 0,
        "notified": False,
    }
