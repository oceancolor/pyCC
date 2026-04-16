# 原始 TS: utils/streamProcessor.ts
"""流式响应处理器"""
from __future__ import annotations
import asyncio
from typing import Any, AsyncIterator, Callable, Optional


class StreamProcessor:
    """处理 Anthropic 流式响应，提取文本和工具调用"""

    def __init__(self, on_text: Optional[Callable[[str], None]] = None,
                 on_tool_use: Optional[Callable[[dict], None]] = None) -> None:
        self._on_text = on_text
        self._on_tool_use = on_tool_use
        self._text_buffer = ""
        self._current_tool: Optional[dict] = None

    def process_event(self, event: Any) -> None:
        event_type = getattr(event, "type", None)
        if event_type == "content_block_start":
            block = event.content_block
            if hasattr(block, "type") and block.type == "tool_use":
                self._current_tool = {
                    "id": block.id, "name": block.name, "input": {}
                }
        elif event_type == "content_block_delta":
            delta = event.delta
            if hasattr(delta, "text"):
                self._text_buffer += delta.text
                if self._on_text:
                    self._on_text(delta.text)
        elif event_type == "content_block_stop":
            if self._current_tool and self._on_tool_use:
                self._on_tool_use(self._current_tool)
            self._current_tool = None

    def get_full_text(self) -> str:
        return self._text_buffer

    def reset(self) -> None:
        self._text_buffer = ""
        self._current_tool = None
