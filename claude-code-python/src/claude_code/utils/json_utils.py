# Source: utils/json.ts
"""JSON and JSONL utilities: safe parsing, JSONL file reading/writing."""
from __future__ import annotations

import json
import os
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator, Generator, Generic, List, Optional, TypeVar

T = TypeVar("T")

PARSE_CACHE_MAX_KEY_BYTES = 8 * 1024
_parse_cache: "OrderedDict[str, Any]" = OrderedDict()
_parse_cache_max = 50


def _strip_bom(text: str) -> str:
    """Strip UTF-8 BOM if present."""
    return text.lstrip("\ufeff")


def _safe_parse_json_uncached(json_str: str, should_log_error: bool = True) -> Any:
    """Parse JSON string, returning None on failure."""
    try:
        return json.loads(_strip_bom(json_str))
    except (json.JSONDecodeError, ValueError) as e:
        if should_log_error:
            pass  # logging stub
        return None


def safe_parse_json(json_str: Optional[str], should_log_error: bool = True) -> Any:
    """Parse JSON with LRU cache for small inputs. Returns None on failure."""
    if not json_str:
        return None
    if len(json_str.encode()) > PARSE_CACHE_MAX_KEY_BYTES:
        return _safe_parse_json_uncached(json_str, should_log_error)
    if json_str in _parse_cache:
        return _parse_cache[json_str]
    result = _safe_parse_json_uncached(json_str, should_log_error)
    if len(_parse_cache) >= _parse_cache_max:
        _parse_cache.popitem(last=False)
    _parse_cache[json_str] = result
    return result


def safe_parse_jsonc(json_str: Optional[str]) -> Any:
    """Parse JSON with comments (basic: strips // and /* */ comments)."""
    if not json_str:
        return None
    import re
    # Remove // line comments
    cleaned = re.sub(r'//[^\n]*', '', json_str)
    # Remove /* */ block comments
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    return safe_parse_json(cleaned, should_log_error=False)


def parse_jsonl(data: str) -> List[Any]:
    """Parse JSONL string, skipping malformed lines."""
    stripped = _strip_bom(data)
    results = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            pass
    return results


MAX_JSONL_READ_BYTES = 100 * 1024 * 1024  # 100 MB


async def read_jsonl_file(file_path: str) -> List[Any]:
    """Read and parse a JSONL file (async). Reads at most last 100 MB."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _read_jsonl_sync, file_path)


def _read_jsonl_sync(file_path: str) -> List[Any]:
    file_size = os.path.getsize(file_path)
    with open(file_path, "rb") as f:
        if file_size <= MAX_JSONL_READ_BYTES:
            raw = f.read()
        else:
            f.seek(file_size - MAX_JSONL_READ_BYTES)
            raw = f.read()
    # Decode
    text = raw.decode("utf-8", errors="replace")
    # Skip first partial line if we read from offset
    if file_size > MAX_JSONL_READ_BYTES:
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
    return parse_jsonl(text)


async def append_jsonl(file_path: str, obj: Any) -> None:
    """Append a single object as a JSONL line."""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _append_jsonl_sync, file_path, obj)


def _append_jsonl_sync(file_path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


async def write_jsonl(file_path: str, objects: List[Any]) -> None:
    """Write a list of objects as JSONL."""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _write_jsonl_sync, file_path, objects)


def _write_jsonl_sync(file_path: str, objects: List[Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        for obj in objects:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def add_item_to_json_array(content: str, new_item: Any) -> str:
    """Add an item to a JSON array string, preserving formatting."""
    try:
        cleaned = _strip_bom(content).strip()
        if not cleaned:
            return json.dumps([new_item], ensure_ascii=False, indent=4)
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            parsed.append(new_item)
            return json.dumps(parsed, ensure_ascii=False, indent=4)
        else:
            return json.dumps([new_item], ensure_ascii=False, indent=4)
    except (json.JSONDecodeError, ValueError):
        return json.dumps([new_item], ensure_ascii=False, indent=4)


# ---------------------------------------------------------------------------
# Additional helpers ported from json.ts (not yet in this file)
# ---------------------------------------------------------------------------


def extract_json_from_code_block(text: str) -> Optional[str]:
    """
    Extract JSON content from a markdown code block.

    Handles:
      ```json
      { ... }
      ```
      or bare ``` blocks containing JSON.

    Returns the raw JSON string (stripped), or None if no code block found.
    """
    import re as _re

    if not text:
        return None

    # Try ```json ... ``` first
    match = _re.search(r"```(?:json)?\s*\n?(.*?)```", text, _re.DOTALL | _re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        if candidate:
            return candidate

    # Fallback: look for a bare JSON object/array in the text
    return None


def find_first_object(text: str) -> Optional[Any]:
    """
    Find and parse the first complete JSON object or array in an arbitrary
    string (e.g., model output that mixes prose with JSON).

    Algorithm:
    - Scan for the first '{' or '[' character.
    - Walk forward tracking brace/bracket depth and string literals.
    - Attempt json.loads on the candidate substring.
    - Returns the parsed value, or None if nothing valid found.
    """
    import json as _json

    if not text:
        return None

    for start_idx, ch in enumerate(text):
        if ch not in ("{", "["):
            continue

        depth = 0
        in_string = False
        escape_next = False
        opener = ch
        closer = "}" if opener == "{" else "]"

        for end_idx in range(start_idx, len(text)):
            c = text[end_idx]

            if escape_next:
                escape_next = False
                continue

            if c == "\\" and in_string:
                escape_next = True
                continue

            if c == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    candidate = text[start_idx : end_idx + 1]
                    try:
                        return _json.loads(candidate)
                    except (_json.JSONDecodeError, ValueError):
                        break  # malformed — try next start position

    return None


def extract_and_parse_json(text: str) -> Optional[Any]:
    """
    Combined helper: try code-block extraction first, then find_first_object.
    Returns the parsed Python object or None.
    """
    import json as _json

    if not text:
        return None

    # 1. Try code block
    from_block = extract_json_from_code_block(text)
    if from_block:
        try:
            return _json.loads(from_block)
        except (_json.JSONDecodeError, ValueError):
            pass

    # 2. Try finding first object in raw text
    return find_first_object(text)
