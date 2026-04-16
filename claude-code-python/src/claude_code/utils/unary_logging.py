"""
Unary event logging stub. Ported from unaryLogging.ts
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Union


CompletionType = Literal["str_replace_single", "str_replace_multi",
                          "write_file_single", "tool_use_single"]


@dataclass
class UnaryLogEvent:
    completion_type: str
    event: Literal["accept", "reject", "response"]
    language_name: str
    message_id: str
    platform: str
    has_feedback: bool = False


async def log_unary_event(event: UnaryLogEvent) -> None:
    """Stub: analytics not implemented."""
    pass
