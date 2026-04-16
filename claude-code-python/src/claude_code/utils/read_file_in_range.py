"""
Line-oriented file reader with fast path (small files) and streaming path.
原始 TS: utils/readFileInRange.ts

- Fast path: 小文件 (<10 MB) 一次性读入内存分割
- Streaming path: 大文件逐块读取，仅累积目标行范围
- 支持 BOM 剥离、CRLF→LF、maxBytes 截断
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

FAST_PATH_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
STREAM_CHUNK_SIZE = 512 * 1024          # 512 KB


@dataclass
class ReadFileRangeResult:
    content: str
    line_count: int
    total_lines: int
    total_bytes: int
    read_bytes: int
    mtime_ms: float
    truncated_by_bytes: bool = False


class FileTooLargeError(Exception):
    def __init__(self, size: int, limit: int) -> None:
        self.size_in_bytes = size
        self.max_size_bytes = limit
        super().__init__(
            f"File content ({size:,} bytes) exceeds limit ({limit:,} bytes). "
            "Use offset/limit parameters to read specific portions."
        )


async def read_file_in_range(
    file_path: str | Path,
    offset: int = 0,
    max_lines: Optional[int] = None,
    max_bytes: Optional[int] = None,
    *,
    truncate_on_byte_limit: bool = False,
) -> ReadFileRangeResult:
    """按行范围读取文件，返回 [offset, offset+max_lines) 内的内容。"""
    path = Path(file_path)
    if path.is_dir():
        raise IsADirectoryError(f"EISDIR: illegal operation on a directory, read '{path}'")

    stat = path.stat()
    mtime_ms = stat.st_mtime * 1000.0

    if path.is_file() and stat.st_size < FAST_PATH_MAX_SIZE:
        if not truncate_on_byte_limit and max_bytes is not None and stat.st_size > max_bytes:
            raise FileTooLargeError(stat.st_size, max_bytes)
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, path.read_bytes)
        return _fast_path(raw, mtime_ms, offset, max_lines,
                          max_bytes if truncate_on_byte_limit else None)

    return await _streaming_path(path, mtime_ms, offset, max_lines,
                                  max_bytes, truncate_on_byte_limit)


async def count_lines(file_path: str | Path) -> int:
    """快速统计文件行数（流式，内存占用极低）。"""
    path = Path(file_path)

    def _count() -> int:
        n = 0
        with open(path, "rb") as f:
            while chunk := f.read(STREAM_CHUNK_SIZE):
                n += chunk.count(b"\n")
        return n + 1

    return await asyncio.get_event_loop().run_in_executor(None, _count)


def _fast_path(
    raw: bytes,
    mtime_ms: float,
    offset: int,
    max_lines: Optional[int],
    truncate_at: Optional[int],
) -> ReadFileRangeResult:
    text = raw.decode("utf-8", errors="replace")
    if text and ord(text[0]) == 0xFEFF:
        text = text[1:]

    end_line = (offset + max_lines) if max_lines is not None else float("inf")
    selected: list[str] = []
    sel_bytes = 0
    truncated = False
    idx = 0
    pos = 0

    def try_push(line: str) -> bool:
        nonlocal sel_bytes, truncated
        if truncate_at is not None:
            nb = sel_bytes + (1 if selected else 0) + len(line.encode())
            if nb > truncate_at:
                truncated = True
                return False
            sel_bytes = nb
        selected.append(line)
        return True

    while (nl := text.find("\n", pos)) != -1:
        if idx >= offset and idx < end_line and not truncated:
            line = text[pos:nl].rstrip("\r")
            try_push(line)
        idx += 1
        pos = nl + 1

    if idx >= offset and idx < end_line and not truncated:
        try_push(text[pos:].rstrip("\r"))
    idx += 1

    content = "\n".join(selected)
    return ReadFileRangeResult(
        content=content, line_count=len(selected), total_lines=idx,
        total_bytes=len(text.encode()), read_bytes=len(content.encode()),
        mtime_ms=mtime_ms, truncated_by_bytes=truncated,
    )


async def _streaming_path(
    path: Path,
    mtime_ms: float,
    offset: int,
    max_lines: Optional[int],
    max_bytes: Optional[int],
    truncate_mode: bool,
) -> ReadFileRangeResult:
    end_line: float = (offset + max_lines) if max_lines is not None else float("inf")

    selected: list[str] = []
    sel_bytes = 0
    total_read = 0
    truncated = False
    cur_line = 0
    partial = ""
    is_first = True

    def _process() -> ReadFileRangeResult:
        nonlocal sel_bytes, total_read, truncated, cur_line, partial, is_first, end_line

        with open(path, "rb") as f:
            while chunk_b := f.read(STREAM_CHUNK_SIZE):
                total_read += len(chunk_b)
                if not truncate_mode and max_bytes and total_read > max_bytes:
                    raise FileTooLargeError(total_read, max_bytes)

                chunk = chunk_b.decode("utf-8", errors="replace")
                if is_first:
                    is_first = False
                    if chunk and ord(chunk[0]) == 0xFEFF:
                        chunk = chunk[1:]

                data = partial + chunk
                partial = ""
                p = 0
                while (nl := data.find("\n", p)) != -1:
                    if cur_line >= offset and cur_line < end_line:
                        line = data[p:nl].rstrip("\r")
                        if truncate_mode and max_bytes:
                            nb = sel_bytes + (1 if selected else 0) + len(line.encode())
                            if nb > max_bytes:
                                truncated = True
                                end_line = cur_line
                            else:
                                sel_bytes = nb
                                selected.append(line)
                        else:
                            selected.append(line)
                    cur_line += 1
                    p = nl + 1
                if p < len(data) and cur_line >= offset and cur_line < end_line:
                    partial = data[p:]

        # 末尾无换行的最后一行
        line = partial.rstrip("\r")
        if cur_line >= offset and cur_line < end_line:
            if truncate_mode and max_bytes:
                nb = sel_bytes + (1 if selected else 0) + len(line.encode())
                if nb <= max_bytes:
                    selected.append(line)
            else:
                selected.append(line)

        content = "\n".join(selected)
        return ReadFileRangeResult(
            content=content, line_count=len(selected), total_lines=cur_line + 1,
            total_bytes=total_read, read_bytes=len(content.encode()),
            mtime_ms=mtime_ms, truncated_by_bytes=truncated,
        )

    return await asyncio.get_event_loop().run_in_executor(None, _process)
