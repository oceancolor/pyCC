"""Collapse consecutive hook summary messages. Ported from collapseHookSummaries.ts"""
from __future__ import annotations
from typing import List, Any


def _is_labeled_hook_summary(msg: dict) -> bool:
    return (msg.get("type") == "system" and msg.get("subtype") == "stop_hook_summary"
            and msg.get("hookLabel") is not None)


def collapse_hook_summaries(messages: List[dict]) -> List[dict]:
    result: List[dict] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if _is_labeled_hook_summary(msg):
            label = msg["hookLabel"]
            group: List[dict] = []
            while i < len(messages):
                nxt = messages[i]
                if not _is_labeled_hook_summary(nxt) or nxt["hookLabel"] != label:
                    break
                group.append(nxt)
                i += 1
            if len(group) == 1:
                result.append(msg)
            else:
                result.append({**msg,
                    "hookCount": sum(m.get("hookCount", 0) for m in group),
                    "hookInfos": [info for m in group for info in m.get("hookInfos", [])],
                    "hookErrors": [e for m in group for e in m.get("hookErrors", [])],
                    "preventedContinuation": any(m.get("preventedContinuation") for m in group),
                    "hasOutput": any(m.get("hasOutput") for m in group),
                    "totalDurationMs": max((m.get("totalDurationMs") or 0) for m in group),
                })
        else:
            result.append(msg)
            i += 1
    return result
