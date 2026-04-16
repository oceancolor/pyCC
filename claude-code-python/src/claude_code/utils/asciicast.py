# 原始 TS: utils/asciicast.ts
"""Asciicast 格式录制（v2 格式）"""
from __future__ import annotations
import json
import time
from typing import IO, List, Optional


class AscicastRecorder:
    """录制终端会话为 asciicast v2 格式"""

    def __init__(self, width: int = 220, height: int = 50, title: str = "Claude Code") -> None:
        self._width = width
        self._height = height
        self._title = title
        self._start = time.time()
        self._events: List[list] = []

    def write(self, data: str, stream: str = "o") -> None:
        """记录一帧输出"""
        ts = time.time() - self._start
        self._events.append([round(ts, 6), stream, data])

    def header(self) -> dict:
        return {
            "version": 2,
            "width": self._width,
            "height": self._height,
            "timestamp": int(self._start),
            "title": self._title,
            "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"},
        }

    def to_jsonl(self) -> str:
        lines = [json.dumps(self.header())]
        for event in self._events:
            lines.append(json.dumps(event))
        return "\n".join(lines)

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            f.write(self.to_jsonl())
