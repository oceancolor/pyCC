"""Collapse consecutive teammate shutdown messages. Ported from collapseTeammateShutdowns.ts"""
from __future__ import annotations
from typing import List
import uuid as _uuid


def _is_teammate_shutdown(msg: dict) -> bool:
    att = msg.get("attachment", {})
    return (msg.get("type") == "attachment" and att.get("type") == "task_status"
            and att.get("taskType") == "in_process_teammate" and att.get("status") == "completed")


def collapse_teammate_shutdowns(messages: List[dict]) -> List[dict]:
    result: List[dict] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if _is_teammate_shutdown(msg):
            count = 0
            while i < len(messages) and _is_teammate_shutdown(messages[i]):
                count += 1
                i += 1
            if count == 1:
                result.append(msg)
            else:
                result.append({"type": "attachment", "uuid": msg.get("uuid", str(_uuid.uuid4())),
                    "timestamp": msg.get("timestamp"), "attachment": {"type": "teammate_shutdown_batch", "count": count}})
        else:
            result.append(msg)
            i += 1
    return result
