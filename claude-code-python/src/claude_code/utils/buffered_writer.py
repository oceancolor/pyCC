# 原始 TS: utils/bufferedWriter.ts
"""带缓冲的流式输出写入器"""
import sys
from typing import Optional, IO


class BufferedWriter:
    """
    缓冲输出写入器，支持流式逐字符/逐块输出。
    用于将模型流式响应逐步显示给用户。
    """

    def __init__(self, stream: IO = sys.stdout, flush_threshold: int = 80):
        self._stream = stream
        self._buffer: list[str] = []
        self._flush_threshold = flush_threshold

    def write(self, text: str) -> None:
        self._buffer.append(text)
        if len("".join(self._buffer)) >= self._flush_threshold:
            self.flush()

    def flush(self) -> None:
        if self._buffer:
            self._stream.write("".join(self._buffer))
            self._stream.flush()
            self._buffer.clear()

    def writeln(self, text: str = "") -> None:
        self.write(text + "\n")
        self.flush()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.flush()
