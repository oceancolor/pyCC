"""
Transcript search utilities — extract searchable text from conversation
messages and search across a transcript.  Port of transcriptSearch.ts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# Interrupt sentinels rendered as a UI component — exclude from search index.
INTERRUPT_MESSAGE: str = "^C"
INTERRUPT_MESSAGE_FOR_TOOL_USE: str = "^C (tool use)"
SYSTEM_REMINDER_OPEN: str = "<system-reminder>"
SYSTEM_REMINDER_CLOSE: str = "</system-reminder>"
RENDERED_AS_SENTINEL: frozenset[str] = frozenset([INTERRUPT_MESSAGE, INTERRUPT_MESSAGE_FOR_TOOL_USE])

# WeakMap-style cache: id(msg) → lowercased search text (safe for append-only lists)
_search_text_cache: dict[int, str] = {}


@dataclass
class TranscriptSearchResult:
    """A single search hit within a transcript."""
    index: int    # position in the message list
    message: Any  # original message dict
    score: float  # relevance score (higher = more relevant)


def tool_use_search_text(input_data: Any) -> str:
    """Extract searchable text from a tool-use block's input dict (duck-typed)."""
    if not input_data or not isinstance(input_data, dict):
        return ""
    parts: list[str] = []
    for key in ("command", "pattern", "file_path", "path", "prompt",
                "description", "query", "url", "skill"):
        val = input_data.get(key)
        if isinstance(val, str):
            parts.append(val)
    for key in ("args", "files"):
        val = input_data.get(key)
        if isinstance(val, list) and all(isinstance(x, str) for x in val):
            parts.append(" ".join(val))
    return "\n".join(parts)


def tool_result_search_text(result: Any) -> str:
    """Extract searchable text from a tool result's native output (duck-typed)."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return ""
    # Bash/Shell shape
    if isinstance(result.get("stdout"), str):
        stderr = result.get("stderr", "")
        return result["stdout"] + (f"\n{stderr}" if stderr else "")
    # Read tool shape
    file_obj = result.get("file")
    if isinstance(file_obj, dict) and isinstance(file_obj.get("content"), str):
        return file_obj["content"]
    parts: list[str] = []
    for key in ("content", "output", "result", "text", "message"):
        val = result.get(key)
        if isinstance(val, str):
            parts.append(val)
    for key in ("filenames", "lines", "results"):
        val = result.get(key)
        if isinstance(val, list) and all(isinstance(x, str) for x in val):
            parts.append("\n".join(val))
    return "\n".join(parts)


def _strip_system_reminders(text: str) -> str:
    """Remove <system-reminder>…</system-reminder> blocks."""
    while True:
        open_pos = text.find(SYSTEM_REMINDER_OPEN)
        if open_pos < 0:
            break
        close_pos = text.find(SYSTEM_REMINDER_CLOSE, open_pos)
        if close_pos < 0:
            break
        text = text[:open_pos] + text[close_pos + len(SYSTEM_REMINDER_CLOSE):]
    return text


def _compute_search_text(msg: dict[str, Any]) -> str:
    """Compute raw searchable text for one message (pre-lowercase)."""
    msg_type = msg.get("type", "")
    raw = ""
    if msg_type == "user":
        content = msg.get("message", {}).get("content", "")
        if isinstance(content, str):
            raw = "" if content in RENDERED_AS_SENTINEL else content
        elif isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    t = block.get("text", "")
                    if t not in RENDERED_AS_SENTINEL:
                        parts.append(t)
                elif block.get("type") == "tool_result":
                    parts.append(tool_result_search_text(
                        msg.get("toolUseResult") or msg.get("tool_use_result")))
            raw = "\n".join(parts)
    elif msg_type == "assistant":
        content = msg.get("message", {}).get("content", [])
        if isinstance(content, list):
            parts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(tool_use_search_text(block.get("input")))
            raw = "\n".join(parts)
    elif msg_type == "attachment":
        att = msg.get("attachment", {})
        att_type = att.get("type", "")
        if att_type == "relevant_memories":
            raw = "\n".join(m.get("content", "") for m in att.get("memories", [])
                            if isinstance(m, dict))
        elif (att_type == "queued_command"
              and att.get("commandMode") != "task-notification"
              and not att.get("isMeta")):
            p = att.get("prompt", "")
            raw = p if isinstance(p, str) else "\n".join(
                b.get("text", "") for b in p
                if isinstance(b, dict) and b.get("type") == "text")
    elif msg_type == "collapsed_read_search":
        mems = msg.get("relevantMemories", [])
        if mems:
            raw = "\n".join(m.get("content", "") for m in mems if isinstance(m, dict))
    return _strip_system_reminders(raw)


def renderable_search_text(msg: dict[str, Any]) -> str:
    """Return lowercased, cached searchable text for *msg*."""
    key = id(msg)
    cached = _search_text_cache.get(key)
    if cached is not None:
        return cached
    result = _compute_search_text(msg).lower()
    _search_text_cache[key] = result
    return result


def search_transcript(
    messages: list[dict[str, Any]],
    query: str,
) -> list[TranscriptSearchResult]:
    """
    Search *messages* for *query* (case-insensitive substring).

    Returns a list of :class:`TranscriptSearchResult` sorted by score
    descending then index ascending.  Empty list when *query* is blank.
    """
    q = query.strip().lower()
    if not q:
        return []
    results: list[TranscriptSearchResult] = []
    for idx, msg in enumerate(messages):
        text = renderable_search_text(msg)
        count = text.count(q)
        if count > 0:
            results.append(TranscriptSearchResult(index=idx, message=msg, score=float(count)))
    results.sort(key=lambda r: (-r.score, r.index))
    return results


def get_message_indices_for_query(
    messages: list[dict[str, Any]],
    query: str,
) -> list[int]:
    """Return only the matching message indices for *query*."""
    return [r.index for r in search_transcript(messages, query)]
