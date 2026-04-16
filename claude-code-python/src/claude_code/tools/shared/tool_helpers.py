"""Shared tool helpers. Ported from tools/shared/."""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def make_tool_result(content: Any, tool_use_id: str, is_error: bool = False) -> dict:
    if isinstance(content, str):
        block = content
    else:
        import json
        block = json.dumps(content)
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": block,
        "is_error": is_error,
    }


def truncate_tool_result(content: str, max_chars: int = 100_000) -> str:
    if len(content) <= max_chars:
        return content
    half = max_chars // 2
    return content[:half] + f"\n\n[...truncated {len(content) - max_chars} chars...]\n\n" + content[-half:]
