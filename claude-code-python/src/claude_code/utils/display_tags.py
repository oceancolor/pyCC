# 原始 TS: utils/displayTags.ts
"""消息 display tag（折叠/展开、类型标记）"""
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, Optional


class DisplayTag(str, Enum):
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    COLLAPSED = "collapsed"


def tag_message(msg: Dict[str, Any], tag: DisplayTag) -> Dict[str, Any]:
    return {**msg, "_display_tag": tag.value}


def get_tag(msg: Dict[str, Any]) -> Optional[DisplayTag]:
    raw = msg.get("_display_tag")
    if raw:
        try:
            return DisplayTag(raw)
        except ValueError:
            pass
    return None


def should_collapse(msg: Dict[str, Any]) -> bool:
    tag = get_tag(msg)
    return tag in (DisplayTag.THINKING, DisplayTag.TOOL_RESULT, DisplayTag.COLLAPSED)
