"""
Python port of utils/json.ts
Source: claude-code-source/utils/json.ts (277 lines)

JSONL read/write utilities, safe JSON parsing with LRU cache,
and JSON array modification helpers.

Note: Named jsonl.py (not json.py) to avoid shadowing the stdlib json module.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator, Generator, Iterable, Iterator, Optional, TypeVar

from .slow_operations import json_stringify

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# BOM helpers
# ---------------------------------------------------------------------------

_UTF8_BOM = "\ufeff"
_UTF8_BOM_BYTES = b"\xef\xbb\xbf"


def strip_bom(text: str) -> str:
    """Strip a UTF-8 BOM character from the start of a string."""
    if text.startswith(_UTF8_BOM):
        return text[1:]
    return text


def strip_bom_bytes(data: bytes) -> bytes:
    """Strip a UTF-8 BOM byte sequence from the start of bytes."""
    if data[:3] == _UTF8_BOM_BYTES:
        return data[3:]
    return data


# ---------------------------------------------------------------------------
# Safe JSON parsing (memoized for small inputs, mirrors safeParseJSON)
# ---------------------------------------------------------------------------

_PARSE_CACHE_MAX_KEY_BYTES = 8 * 1024  # 8 KB


def _parse_json_uncached(text: str, should_log_error: bool = True) -> tuple[bool, Any]:
    """Return (ok, value) tuple. ok=False means parse failed."""
    try:
        return True, json.loads(strip_bom(text))
    except (json.JSONDecodeError, ValueError) as exc:
        if should_log_error:
            logger.error("JSON parse error: %s", exc)
        return False, None


# LRU-bounded cache for small JSON strings (≤ 8 KB), limited to 50 entries.
@lru_cache(maxsize=50)
def _parse_json_cached(text: str) -> tuple[bool, Any]:
    return _parse_json_uncached(text, should_log_error=False)


def safe_parse_json(
    json_str: Optional[str],
    should_log_error: bool = True,
) -> Any:
    """
    Safely parse a JSON string, returning None on failure.

    Mirrors TS ``safeParseJSON(json, shouldLogError)``.
    Uses an LRU cache (50 entries) for small strings (≤ 8 KB).
    """
    if not json_str:
        return None
    if len(json_str.encode("utf-8")) > _PARSE_CACHE_MAX_KEY_BYTES:
        ok, value = _parse_json_uncached(json_str, should_log_error)
    else:
        ok, value = _parse_json_cached(json_str)
    return value if ok else None


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------

def parse_jsonl_string(data: str) -> list[Any]:
    """
    Parse a JSONL string into a list of objects, skipping malformed lines.

    Mirrors TS ``parseJSONLString``.
    """
    stripped = strip_bom(data)
    results: list[Any] = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            pass  # skip malformed lines
    return results


def parse_jsonl_bytes(data: bytes) -> list[Any]:
    """
    Parse JSONL from raw bytes, stripping BOM, skipping malformed lines.

    Mirrors TS ``parseJSONLBuffer``.
    """
    cleaned = strip_bom_bytes(data)
    results: list[Any] = []
    for line_bytes in cleaned.split(b"\n"):
        line = line_bytes.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line.decode("utf-8", errors="replace")))
        except (json.JSONDecodeError, ValueError):
            pass
    return results


def parse_jsonl(data: str | bytes) -> list[Any]:
    """
    Parse JSONL data from a string or bytes, skipping malformed lines.

    Mirrors TS ``parseJSONL``.
    """
    if isinstance(data, bytes):
        return parse_jsonl_bytes(data)
    return parse_jsonl_string(data)


# ---------------------------------------------------------------------------
# JSONL file I/O (sync versions)
# ---------------------------------------------------------------------------

_MAX_JSONL_READ_BYTES = 100 * 1024 * 1024  # 100 MB


def read_jsonl_file(file_path: str | Path) -> list[Any]:
    """
    Read and parse a JSONL file, reading at most the last 100 MB.

    For files larger than 100 MB, reads the tail and skips the first
    partial line (mirrors TS ``readJSONLFile``).
    """
    path = Path(file_path)
    size = path.stat().st_size

    if size <= _MAX_JSONL_READ_BYTES:
        raw = path.read_bytes()
        return parse_jsonl(raw)

    # Large file: read the tail
    file_offset = size - _MAX_JSONL_READ_BYTES
    with open(path, "rb") as fh:
        fh.seek(file_offset)
        buf = fh.read(_MAX_JSONL_READ_BYTES)

    # Skip the first partial line
    newline_idx = buf.find(b"\n")
    if newline_idx != -1 and newline_idx < len(buf) - 1:
        buf = buf[newline_idx + 1 :]

    return parse_jsonl(buf)


def iter_jsonl_file(file_path: str | Path) -> Iterator[Any]:
    """
    Iterate over parsed objects in a JSONL file line by line.

    Memory-efficient alternative to ``read_jsonl_file`` for large files.
    Yields parsed objects, silently skipping malformed lines.
    """
    path = Path(file_path)
    with open(path, "r", encoding="utf-8-sig") as fh:  # utf-8-sig strips BOM
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (json.JSONDecodeError, ValueError):
                pass


def append_jsonl(file_path: str | Path, obj: Any) -> None:
    """
    Append a single object as a JSONL line to a file.
    Creates the file (and parent directories) if it doesn't exist.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json_stringify(obj) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)


def write_jsonl(file_path: str | Path, objects: Iterable[Any]) -> None:
    """
    Write an iterable of objects to a JSONL file (overwrites existing content).
    Creates the file (and parent directories) if it doesn't exist.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for obj in objects:
            fh.write(json_stringify(obj) + "\n")


# ---------------------------------------------------------------------------
# Async JSONL file I/O
# ---------------------------------------------------------------------------

async def read_jsonl_file_async(file_path: str | Path) -> list[Any]:
    """
    Async version of ``read_jsonl_file``.
    Delegates to the sync version via a thread-pool executor.
    """
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, read_jsonl_file, file_path)


async def append_jsonl_async(file_path: str | Path, obj: Any) -> None:
    """Async version of ``append_jsonl``."""
    import asyncio

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, append_jsonl, file_path, obj)


async def write_jsonl_async(file_path: str | Path, objects: list[Any]) -> None:
    """Async version of ``write_jsonl``."""
    import asyncio

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, write_jsonl, file_path, objects)


# ---------------------------------------------------------------------------
# JSON array modification helper (mirrors addItemToJSONCArray)
# ---------------------------------------------------------------------------

def add_item_to_json_array(content: str, new_item: Any) -> str:
    """
    Add an item to a JSON array string, preserving formatting as much as possible.

    If ``content`` is empty or not a valid JSON array, a new array is created.
    Mirrors TS ``addItemToJSONCArray``.
    """
    if not content or not content.strip():
        return json.dumps([new_item], indent=4)

    cleaned = strip_bom(content)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            parsed.append(new_item)
            return json.dumps(parsed, indent=4)
        # Not an array — replace with new array
        return json.dumps([new_item], indent=4)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("add_item_to_json_array parse error: %s", exc)
        return json.dumps([new_item], indent=4)
