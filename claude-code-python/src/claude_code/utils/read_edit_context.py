"""
read_edit_context.py - File context scanning around a needle string.

Ported from readEditContext.ts. Provides efficient file scanning to locate
a target string and return surrounding context lines, handling:
- Large files via chunked I/O (CHUNK_SIZE = 8KB)
- Cross-chunk boundary matches via overlap buffer
- CRLF normalization
- Capped scan at MAX_SCAN_BYTES (10MB)
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional

CHUNK_SIZE = 8 * 1024          # 8 KB
MAX_SCAN_BYTES = 10 * 1024 * 1024  # 10 MB


@dataclass
class EditContext:
    """Context window slice around a matched needle in a file."""
    content: str
    """Slice of the file: contextLines before/after the match, line-aligned."""
    line_offset: int
    """1-based line number of content's first line in the original file."""
    truncated: bool
    """True if MAX_SCAN_BYTES was hit without finding the needle."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def read_edit_context(
    path: str,
    needle: str,
    context_lines: int = 3,
) -> Optional[EditContext]:
    """
    Find *needle* in the file at *path* and return a context-window slice.

    Scans in CHUNK_SIZE chunks with overlap so matches crossing chunk
    boundaries are found. Capped at MAX_SCAN_BYTES.

    Returns None on ENOENT.
    Returns EditContext(truncated=True, content='') if needle not found
    within MAX_SCAN_BYTES.
    """
    try:
        f = open(path, "rb")
    except FileNotFoundError:
        return None

    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _scan_for_context_sync, f, needle, context_lines
        )
    finally:
        f.close()


async def read_capped(path: str) -> Optional[str]:
    """
    Read the entire file (up to MAX_SCAN_BYTES). Returns None if the file
    exceeds the cap. Normalizes CRLF to LF.
    """
    try:
        f = open(path, "rb")
    except FileNotFoundError:
        return None

    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _read_capped_sync, f
        )
    finally:
        f.close()


# ---------------------------------------------------------------------------
# Synchronous core (run in executor to avoid blocking event loop)
# ---------------------------------------------------------------------------

def _scan_for_context_sync(
    f,
    needle: str,
    context_lines: int,
) -> EditContext:
    if not needle:
        return EditContext(content="", line_offset=1, truncated=False)

    needle_lf = needle.encode("utf-8")
    nl_count = needle_lf.count(b"\n")
    needle_crlf: Optional[bytes] = None
    overlap = len(needle_lf) + nl_count - 1
    overlap = max(overlap, 0)

    buf = bytearray(CHUNK_SIZE + overlap)
    pos = 0
    lines_before_pos = 0
    prev_tail = 0

    while pos < MAX_SCAN_BYTES:
        f.seek(pos)
        chunk = f.read(CHUNK_SIZE)
        if not chunk:
            break
        bytes_read = len(chunk)
        view_len = prev_tail + bytes_read
        buf[prev_tail:prev_tail + bytes_read] = chunk

        data = bytes(buf[:view_len])
        match_at, match_len = _find_needle(data, needle_lf, needle_crlf, nl_count)

        if needle_crlf is None and nl_count > 0 and match_at == -1:
            needle_crlf = needle.replace("\n", "\r\n").encode("utf-8")
            match_at, match_len = _find_needle(data, needle_lf, needle_crlf, nl_count)

        if match_at != -1:
            abs_match = pos - prev_tail + match_at
            lines_before_match = lines_before_pos + data[:match_at].count(b"\n")
            return _slice_context_sync(
                f, abs_match, match_len, context_lines, lines_before_match
            )

        pos += bytes_read
        next_tail = min(overlap, view_len)
        # Count newlines in discarded portion
        lines_before_pos += data[: view_len - next_tail].count(b"\n")
        prev_tail = next_tail
        buf[:next_tail] = data[view_len - next_tail: view_len]

    return EditContext(
        content="",
        line_offset=1,
        truncated=pos >= MAX_SCAN_BYTES,
    )


def _find_needle(
    data: bytes,
    needle_lf: bytes,
    needle_crlf: Optional[bytes],
    nl_count: int,
) -> tuple[int, int]:
    idx = data.find(needle_lf)
    if idx != -1:
        return idx, len(needle_lf)
    if nl_count > 0 and needle_crlf:
        idx2 = data.find(needle_crlf)
        if idx2 != -1:
            return idx2, len(needle_crlf)
    return -1, 0


def _slice_context_sync(
    f,
    match_start: int,
    match_len: int,
    context_lines: int,
    lines_before_match: int,
) -> EditContext:
    """Read ±context_lines around the match and return the decoded slice."""
    # Scan backward to find context_lines prior newlines
    back_size = min(match_start, CHUNK_SIZE)
    f.seek(match_start - back_size)
    back_data = f.read(back_size)

    ctx_start = match_start
    nl_seen = 0
    for i in range(len(back_data) - 1, -1, -1):
        if back_data[i] == ord(b"\n"):
            nl_seen += 1
            if nl_seen > context_lines:
                break
        ctx_start -= 1

    walked_back = match_start - ctx_start
    line_offset = (
        lines_before_match
        - back_data[len(back_data) - walked_back:].count(b"\n")
        + 1
    )

    # Scan forward to find context_lines trailing newlines
    match_end = match_start + match_len
    f.seek(match_end)
    fwd_data = f.read(CHUNK_SIZE)

    ctx_end = match_end
    nl_seen = 0
    for byte in fwd_data:
        ctx_end += 1
        if byte == ord(b"\n"):
            nl_seen += 1
            if nl_seen >= context_lines + 1:
                break

    # Read exact context range
    length = ctx_end - ctx_start
    f.seek(ctx_start)
    raw = f.read(length)

    content = _normalize_crlf(raw)
    return EditContext(content=content, line_offset=line_offset, truncated=False)


def _read_capped_sync(f) -> Optional[str]:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = f.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_SCAN_BYTES:
            return None
        chunks.append(chunk)
    raw = b"".join(chunks)
    return _normalize_crlf(raw)


def _normalize_crlf(data: bytes) -> str:
    s = data.decode("utf-8", errors="replace")
    return s.replace("\r\n", "\n") if "\r" in s else s
