"""
Session history management.
Ported from history.ts (464 lines → core).
"""
from __future__ import annotations
import os
import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional, TypedDict

MAX_HISTORY_ITEMS = 100
MAX_PASTED_CONTENT_LENGTH = 1024

_pending_entries: List[Any] = []


def get_pasted_text_ref_num_lines(text: str) -> int:
    return len(re.findall(r"\r\n|\r|\n", text))


def format_pasted_text_ref(id: int, num_lines: int) -> str:
    return f"[Pasted text #{id} +{num_lines} lines]"


def format_image_ref(id: int) -> str:
    return f"[Image #{id}]"


PASTED_TEXT_REF_PATTERN = re.compile(r"\[Pasted text #(\d+) \+(\d+) lines\]")
IMAGE_REF_PATTERN = re.compile(r"\[Image #(\d+)\]")


def parse_references(text: str) -> List[Dict]:
    refs = []
    for m in PASTED_TEXT_REF_PATTERN.finditer(text):
        refs.append({"type": "text", "id": int(m.group(1)), "num_lines": int(m.group(2))})
    for m in IMAGE_REF_PATTERN.finditer(text):
        refs.append({"type": "image", "id": int(m.group(1))})
    return refs


def expand_pasted_text_refs(text: str, paste_store: Dict[int, str]) -> str:
    def _replace_text(m: re.Match) -> str:
        ref_id = int(m.group(1))
        return paste_store.get(ref_id, m.group(0))
    return PASTED_TEXT_REF_PATTERN.sub(_replace_text, text)


def _get_history_path() -> str:
    claude_home = os.environ.get("CLAUDE_CONFIG_HOME",
                                  os.path.join(os.path.expanduser("~"), ".claude"))
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "default")
    cwd_safe = os.getcwd().replace("/", "_").lstrip("_")
    history_dir = os.path.join(claude_home, "history")
    os.makedirs(history_dir, exist_ok=True)
    return os.path.join(history_dir, f"{cwd_safe}-{session_id}.jsonl")


def add_to_history(entry: Any) -> None:
    _pending_entries.append(entry)
    path = _get_history_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def clear_pending_history_entries() -> None:
    _pending_entries.clear()


def remove_last_from_history() -> None:
    if _pending_entries:
        _pending_entries.pop()
    path = _get_history_path()
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[:-1])
    except OSError:
        pass


class TimestampedHistoryEntry(TypedDict):
    entry: Any
    timestamp: float
    session_id: str


async def get_history() -> AsyncIterator[Any]:
    path = _get_history_path()
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass


async def make_history_reader() -> AsyncIterator[Any]:
    return get_history()
