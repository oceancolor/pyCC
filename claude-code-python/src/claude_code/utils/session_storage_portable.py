"""
Portable session storage utilities.

Pure Python — no internal dependencies on logging, experiments, or feature
flags. Shared between the CLI and SDK layers.

原始 TS: utils/sessionStoragePortable.ts (793 行)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from claude_code.utils.env_utils import get_claude_config_home_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Size of the head/tail buffer for lite metadata reads (64 KB).
LITE_READ_BUF_SIZE = 65536

#: Maximum length for a single filesystem path component.
MAX_SANITIZED_LENGTH = 200

#: File size below which precompact filtering is skipped (5 MB).
SKIP_PRECOMPACT_THRESHOLD = 5 * 1024 * 1024

#: Chunk size for forward transcript reader (1 MB).
TRANSCRIPT_READ_CHUNK_SIZE = 1024 * 1024

# ---------------------------------------------------------------------------
# UUID validation
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_uuid(maybe_uuid: Any) -> Optional[str]:
    """Return *maybe_uuid* as a validated UUID string, or ``None``."""
    if not isinstance(maybe_uuid, str):
        return None
    return maybe_uuid if _UUID_RE.match(maybe_uuid) else None


# ---------------------------------------------------------------------------
# JSON string field extraction — no full parse, works on truncated lines
# ---------------------------------------------------------------------------


def unescape_json_string(raw: str) -> str:
    """Unescape a JSON string value extracted as raw text.

    Only allocates a new string when escape sequences are present.
    """
    if "\\" not in raw:
        return raw
    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw


def extract_json_string_field(text: str, key: str) -> Optional[str]:
    """Extract a simple JSON string field value from raw text without full parsing.

    Looks for ``"key":"value"`` or ``"key": "value"`` patterns.
    Returns the first match, or ``None`` if not found.
    """
    patterns = [f'"{key}":"', f'"{key}": "']
    for pattern in patterns:
        idx = text.find(pattern)
        if idx < 0:
            continue
        value_start = idx + len(pattern)
        i = value_start
        while i < len(text):
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == '"':
                return unescape_json_string(text[value_start:i])
            i += 1
    return None


def extract_last_json_string_field(text: str, key: str) -> Optional[str]:
    """Like :func:`extract_json_string_field` but returns the *last* occurrence."""
    patterns = [f'"{key}":"', f'"{key}": "']
    last_value: Optional[str] = None
    for pattern in patterns:
        search_from = 0
        while True:
            idx = text.find(pattern, search_from)
            if idx < 0:
                break
            value_start = idx + len(pattern)
            i = value_start
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    last_value = unescape_json_string(text[value_start:i])
                    break
                i += 1
            search_from = i + 1
    return last_value


# ---------------------------------------------------------------------------
# First prompt extraction from head chunk
# ---------------------------------------------------------------------------

_SKIP_FIRST_PROMPT_RE = re.compile(
    r"^(?:\s*<[a-z][\w-]*[\s>]|\[Request interrupted by user[^\]]*\])"
)
_COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>")
_BASH_INPUT_RE = re.compile(r"<bash-input>([\s\S]*?)</bash-input>")


def extract_first_prompt_from_head(head: str) -> str:
    """Extract the first meaningful user prompt from a JSONL head chunk.

    Skips tool_result messages, isMeta, isCompactSummary, command-name messages,
    and auto-generated patterns. Truncates to 200 chars.
    """
    start = 0
    command_fallback = ""
    while start < len(head):
        newline_idx = head.find("\n", start)
        if newline_idx >= 0:
            line = head[start:newline_idx]
            start = newline_idx + 1
        else:
            line = head[start:]
            start = len(head)

        if '"type":"user"' not in line and '"type": "user"' not in line:
            continue
        if '"tool_result"' in line:
            continue
        if '"isMeta":true' in line or '"isMeta": true' in line:
            continue
        if '"isCompactSummary":true' in line or '"isCompactSummary": true' in line:
            continue

        try:
            entry: Dict[str, Any] = json.loads(line)
        except Exception:
            continue

        if entry.get("type") != "user":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")

        texts: List[str] = []
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                ):
                    texts.append(block["text"])

        for raw in texts:
            result = raw.replace("\n", " ").strip()
            if not result:
                continue

            cmd_match = _COMMAND_NAME_RE.search(result)
            if cmd_match:
                if not command_fallback:
                    command_fallback = cmd_match.group(1)
                continue

            bash_match = _BASH_INPUT_RE.search(result)
            if bash_match:
                return f"! {bash_match.group(1).strip()}"

            if _SKIP_FIRST_PROMPT_RE.match(result):
                continue

            if len(result) > 200:
                result = result[:200].rstrip() + "\u2026"
            return result

    return command_fallback


# ---------------------------------------------------------------------------
# File I/O — read head and tail of a file
# ---------------------------------------------------------------------------


class LiteSessionFile:
    """Lightweight representation of a session file's metadata + head/tail text."""

    __slots__ = ("mtime", "size", "head", "tail")

    def __init__(self, mtime: float, size: int, head: str, tail: str) -> None:
        self.mtime = mtime
        self.size = size
        self.head = head
        self.tail = tail


async def read_head_and_tail(
    file_path: str,
    file_size: int,
    buf: bytearray,
) -> Tuple[str, str]:
    """Read the first and last ``LITE_READ_BUF_SIZE`` bytes of a file.

    For small files where head covers tail, ``tail == head``.
    Returns ``("", "")`` on any error.
    """
    try:
        loop = asyncio.get_event_loop()

        def _read() -> Tuple[str, str]:
            with open(file_path, "rb") as fh:
                raw = fh.read(LITE_READ_BUF_SIZE)
                if not raw:
                    return ("", "")
                head = raw.decode("utf-8", errors="replace")

                tail_offset = max(0, file_size - LITE_READ_BUF_SIZE)
                if tail_offset > 0:
                    fh.seek(tail_offset)
                    tail_raw = fh.read(LITE_READ_BUF_SIZE)
                    tail = tail_raw.decode("utf-8", errors="replace")
                else:
                    tail = head
            return (head, tail)

        return await loop.run_in_executor(None, _read)
    except Exception:
        return ("", "")


async def read_session_lite(file_path: str) -> Optional[LiteSessionFile]:
    """Open a single session file, stat it, and read head + tail.

    Returns ``None`` on any error.
    """
    try:
        loop = asyncio.get_event_loop()

        def _read() -> Optional[LiteSessionFile]:
            try:
                stat = os.stat(file_path)
                file_size = stat.st_size
                mtime = stat.st_mtime

                with open(file_path, "rb") as fh:
                    raw = fh.read(LITE_READ_BUF_SIZE)
                    if not raw:
                        return None
                    head = raw.decode("utf-8", errors="replace")

                    tail_offset = max(0, file_size - LITE_READ_BUF_SIZE)
                    if tail_offset > 0:
                        fh.seek(tail_offset)
                        tail_raw = fh.read(LITE_READ_BUF_SIZE)
                        tail = tail_raw.decode("utf-8", errors="replace")
                    else:
                        tail = head
                return LiteSessionFile(mtime=mtime, size=file_size, head=head, tail=tail)
            except Exception:
                return None

        return await loop.run_in_executor(None, _read)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Path sanitization
# ---------------------------------------------------------------------------


def _djb2_hash(s: str) -> int:
    """DJB2 hash algorithm (same as TypeScript reference implementation)."""
    h = 5381
    for ch in s.encode("utf-8"):
        h = ((h << 5) + h + ch) & 0xFFFFFFFF
    # Convert to signed 32-bit
    if h >= 0x80000000:
        h -= 0x100000000
    return h


def _simple_hash(s: str) -> str:
    """Compute a short base-36 hash of *s* using DJB2."""
    return str(abs(_djb2_hash(s)), )


def _simple_hash_b36(s: str) -> str:
    n = abs(_djb2_hash(s))
    if n == 0:
        return "0"
    digits = []
    while n:
        digits.append("0123456789abcdefghijklmnopqrstuvwxyz"[n % 36])
        n //= 36
    return "".join(reversed(digits))


def sanitize_path(name: str) -> str:
    """Make *name* safe for use as a directory or file name.

    Replaces all non-alphanumeric characters with hyphens. For paths that
    exceed ``MAX_SANITIZED_LENGTH``, truncates and appends a hash suffix.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9]", "-", name)
    if len(sanitized) <= MAX_SANITIZED_LENGTH:
        return sanitized
    hash_suffix = _simple_hash_b36(name)
    return f"{sanitized[:MAX_SANITIZED_LENGTH]}-{hash_suffix}"


# ---------------------------------------------------------------------------
# Project directory discovery
# ---------------------------------------------------------------------------


def get_projects_dir() -> str:
    """Return the path to ``~/.claude/projects/``."""
    return os.path.join(get_claude_config_home_dir(), "projects")


def get_project_dir(project_dir: str) -> str:
    """Return the on-disk directory for *project_dir*."""
    return os.path.join(get_projects_dir(), sanitize_path(project_dir))


async def canonicalize_path(dir_path: str) -> str:
    """Resolve *dir_path* to its canonical form (realpath + NFC normalization).

    Falls back to NFC-only if ``realpath`` fails (e.g. the directory does not
    exist yet).
    """
    try:
        resolved = await asyncio.get_event_loop().run_in_executor(
            None, os.path.realpath, dir_path
        )
        return unicodedata.normalize("NFC", resolved)
    except Exception:
        return unicodedata.normalize("NFC", dir_path)


async def find_project_dir(project_path: str) -> Optional[str]:
    """Find the project directory for *project_path*.

    Tolerates hash mismatches for long paths by falling back to prefix-based
    scanning when the exact match does not exist.
    """
    exact = get_project_dir(project_path)
    loop = asyncio.get_event_loop()

    def _readdir(p: str) -> Optional[List[str]]:
        try:
            return os.listdir(p)
        except Exception:
            return None

    entries = await loop.run_in_executor(None, _readdir, exact)
    if entries is not None:
        return exact

    sanitized = sanitize_path(project_path)
    if len(sanitized) <= MAX_SANITIZED_LENGTH:
        return None

    prefix = sanitized[:MAX_SANITIZED_LENGTH]
    projects_dir = get_projects_dir()

    def _scan():
        try:
            with os.scandir(projects_dir) as it:
                for entry in it:
                    if entry.is_dir() and entry.name.startswith(prefix + "-"):
                        return os.path.join(projects_dir, entry.name)
        except Exception:
            pass
        return None

    return await loop.run_in_executor(None, _scan)


async def resolve_session_file_path(
    session_id: str,
    dir_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve *session_id* to its on-disk JSONL file path.

    Returns a dict ``{"file_path": str, "project_path": str|None, "file_size": int}``
    or ``None`` if not found.
    """
    file_name = f"{session_id}.jsonl"
    loop = asyncio.get_event_loop()

    def _stat(p: str) -> Optional[int]:
        try:
            s = os.stat(p)
            return s.st_size if s.st_size > 0 else None
        except Exception:
            return None

    if dir_path is not None:
        canonical = await canonicalize_path(dir_path)
        project_dir = await find_project_dir(canonical)
        if project_dir:
            file_path = os.path.join(project_dir, file_name)
            size = await loop.run_in_executor(None, _stat, file_path)
            if size is not None:
                return {"file_path": file_path, "project_path": canonical, "file_size": size}

        # Worktree fallback — try to get sibling worktree paths
        worktree_paths: List[str] = []
        try:
            from claude_code.utils.get_worktree_paths_portable import (
                get_worktree_paths_portable,
            )
            worktree_paths = await get_worktree_paths_portable(canonical)
        except Exception:
            pass

        for wt in worktree_paths:
            if wt == canonical:
                continue
            wt_project_dir = await find_project_dir(wt)
            if not wt_project_dir:
                continue
            file_path = os.path.join(wt_project_dir, file_name)
            size = await loop.run_in_executor(None, _stat, file_path)
            if size is not None:
                return {"file_path": file_path, "project_path": wt, "file_size": size}
        return None

    # No dir — scan all project directories
    projects_dir = get_projects_dir()

    def _scan_all():
        try:
            names = os.listdir(projects_dir)
        except Exception:
            return None
        for name in names:
            fp = os.path.join(projects_dir, name, file_name)
            try:
                s = os.stat(fp)
                if s.st_size > 0:
                    return {"file_path": fp, "project_path": None, "file_size": s.st_size}
            except Exception:
                continue
        return None

    return await loop.run_in_executor(None, _scan_all)


# ---------------------------------------------------------------------------
# Session JSONL helpers (save / load / list)
# ---------------------------------------------------------------------------


async def save_session_message(
    session_id: str,
    cwd: str,
    message: Any,
) -> None:
    """Persist *message* (any JSON-serialisable object) to the session JSONL file."""
    canonical = await canonicalize_path(cwd)
    project_dir_path = get_project_dir(canonical)

    loop = asyncio.get_event_loop()

    def _write():
        os.makedirs(project_dir_path, exist_ok=True)
        file_path = os.path.join(project_dir_path, f"{session_id}.jsonl")
        line = json.dumps(message, ensure_ascii=False) + "\n"
        with open(file_path, "a", encoding="utf-8") as fh:
            fh.write(line)

    await loop.run_in_executor(None, _write)


async def load_session_messages(
    session_id: str,
    cwd: str,
) -> List[Any]:
    """Load all messages from the session JSONL file.

    Returns an empty list if the file does not exist or is empty.
    """
    result = await resolve_session_file_path(session_id, cwd)
    if result is None:
        return []

    file_path: str = result["file_path"]
    loop = asyncio.get_event_loop()

    def _load():
        messages = []
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        messages.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            pass
        return messages

    return await loop.run_in_executor(None, _load)


async def list_sessions(cwd: str) -> List[Dict[str, Any]]:
    """List all sessions for the project rooted at *cwd*.

    Returns a list of dicts with ``session_id``, ``file_path``, ``mtime``,
    ``size``, ``head``, and ``tail``.
    """
    canonical = await canonicalize_path(cwd)
    project_dir_path = await find_project_dir(canonical)
    if not project_dir_path:
        return []

    loop = asyncio.get_event_loop()

    def _list_files() -> List[str]:
        try:
            return [
                os.path.join(project_dir_path, n)
                for n in os.listdir(project_dir_path)
                if n.endswith(".jsonl")
            ]
        except Exception:
            return []

    file_paths = await loop.run_in_executor(None, _list_files)
    tasks = [read_session_lite(fp) for fp in file_paths]
    lite_results = await asyncio.gather(*tasks)

    sessions = []
    for fp, lite in zip(file_paths, lite_results):
        if lite is None:
            continue
        session_id = os.path.splitext(os.path.basename(fp))[0]
        sessions.append(
            {
                "session_id": session_id,
                "file_path": fp,
                "mtime": lite.mtime,
                "size": lite.size,
                "head": lite.head,
                "tail": lite.tail,
            }
        )
    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    return sessions


# ---------------------------------------------------------------------------
# Compact-boundary chunked read
# ---------------------------------------------------------------------------

_COMPACT_BOUNDARY_MARKER = b'"compact_boundary"'
_ATTR_SNAP_PREFIX = b'{"type":"attribution-snapshot"'
_SYSTEM_PREFIX = b'{"type":"system"'
_BOUNDARY_SEARCH_BOUND = 256


def _parse_boundary_line(line: str) -> Optional[Dict[str, Any]]:
    """Confirm a byte-matched line is a real compact_boundary entry."""
    try:
        parsed = json.loads(line)
        if parsed.get("type") != "system" or parsed.get("subtype") != "compact_boundary":
            return None
        return {
            "has_preserved_segment": bool(
                parsed.get("compactMetadata", {}).get("preservedSegment")
            )
        }
    except Exception:
        return None


async def read_transcript_for_load(
    file_path: str,
    file_size: int,
) -> Dict[str, Any]:
    """Single forward chunked read for the --resume load path.

    Returns a dict with keys:
    - ``boundary_start_offset``: int
    - ``post_boundary_buf``: bytes
    - ``has_preserved_segment``: bool
    """
    loop = asyncio.get_event_loop()

    def _read() -> Dict[str, Any]:
        marker = _COMPACT_BOUNDARY_MARKER
        out = bytearray()
        boundary_start_offset = 0
        has_preserved_segment = False
        last_snap: Optional[bytes] = None
        carry = bytearray()

        with open(file_path, "rb") as fh:
            file_pos = 0
            while file_pos < file_size:
                to_read = min(TRANSCRIPT_READ_CHUNK_SIZE, file_size - file_pos)
                chunk = fh.read(to_read)
                if not chunk:
                    break
                file_pos += len(chunk)

                buf = bytes(carry) + chunk
                carry = bytearray()

                lines = buf.split(b"\n")
                # Last element may be incomplete (no trailing newline)
                carry.extend(lines[-1])
                complete_lines = lines[:-1]

                for raw_line in complete_lines:
                    line_b = raw_line + b"\n"

                    if raw_line.startswith(_ATTR_SNAP_PREFIX):
                        # Skip attr-snap lines from output; remember as last snap
                        last_snap = line_b
                        continue

                    if marker in raw_line and raw_line.startswith(_SYSTEM_PREFIX):
                        hit = _parse_boundary_line(raw_line.decode("utf-8", errors="replace"))
                        if hit is not None:
                            if hit["has_preserved_segment"]:
                                has_preserved_segment = True
                            else:
                                out = bytearray()
                                boundary_start_offset = file_pos - len(chunk)
                                has_preserved_segment = False
                                last_snap = None
                            continue

                    out.extend(line_b)

            # Handle any trailing carry (incomplete final line)
            if carry:
                if carry.startswith(_ATTR_SNAP_PREFIX):
                    last_snap = bytes(carry)
                else:
                    out.extend(carry)

        # Append last attr-snap at EOF
        if last_snap:
            if out and out[-1] != ord(b"\n"):
                out.extend(b"\n")
            out.extend(last_snap)

        return {
            "boundary_start_offset": boundary_start_offset,
            "post_boundary_buf": bytes(out),
            "has_preserved_segment": has_preserved_segment,
        }

    return await loop.run_in_executor(None, _read)
