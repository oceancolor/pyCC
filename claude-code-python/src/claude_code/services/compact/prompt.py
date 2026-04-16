"""Compact prompt builder. Ported from services/compact/prompt.ts"""
from __future__ import annotations
from typing import List, Optional

COMPACT_SYSTEM_PROMPT = """Your task is to create a concise yet comprehensive summary of the conversation so far.
This summary will replace earlier parts of the conversation to save context.
Include: key decisions, code changes, current task status, and important technical details."""


def build_compact_prompt(messages: List[dict], focus: Optional[str] = None) -> str:
    msg_count = len(messages)
    focus_str = f" Focus on: {focus}." if focus else ""
    return f"Please summarize the last {msg_count} messages.{focus_str}"
