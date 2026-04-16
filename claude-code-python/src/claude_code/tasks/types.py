"""Task state union types. Ported from tasks/types.ts"""
from __future__ import annotations
from typing import Any, Dict, Union


def is_background_task(task: dict) -> bool:
    if task.get("status") not in ("running", "pending"):
        return False
    if "is_backgrounded" in task and task["is_backgrounded"] is False:
        return False
    return True
