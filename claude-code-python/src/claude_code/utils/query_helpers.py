"""
Query helper utilities for tool execution and message processing.

Ports the core logic from queryHelpers.ts while stubbing out internal
dependencies (session persistence, file state cache, etc.) that are not
yet part of this Python layer.

原始 TS: utils/queryHelpers.ts (552 行)
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Type aliases / stubs
# ---------------------------------------------------------------------------

# A "Message" is a plain dict with at minimum a "type" key.
Message = Dict[str, Any]

# A "Tool" is a callable that handles a tool_use block.
# Signature: async (name, input, tool_use_id) -> Any
ToolCallable = Callable[[str, Dict[str, Any], str], Any]

# Map from tool name → callable
Tools = Dict[str, ToolCallable]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_TOOL_PROGRESS_TRACKING_ENTRIES = 100
TOOL_PROGRESS_THROTTLE_MS = 30_000

# ---------------------------------------------------------------------------
# isResultSuccessful
# ---------------------------------------------------------------------------


def is_result_successful(
    message: Optional[Message],
    stop_reason: Optional[str] = None,
) -> bool:
    """Return ``True`` when the last-message result should be considered successful.

    Mirrors the TypeScript ``isResultSuccessful`` function.

    Returns ``True`` if:
    - Last message is ``assistant`` with text/thinking content
    - Last message is ``user`` with only ``tool_result`` blocks
    - stop_reason is ``"end_turn"`` (model chose to emit no content blocks)
    """
    if message is None:
        return False

    msg_type = message.get("type")

    if msg_type == "assistant":
        msg = message.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, list) and content:
            last_block = content[-1]
            return last_block.get("type") in ("text", "thinking", "redacted_thinking")
        return False

    if msg_type == "user":
        msg = message.get("message", {})
        content = msg.get("content", [])
        if (
            isinstance(content, list)
            and content
            and all(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            )
        ):
            return True

    return stop_reason == "end_turn"


# ---------------------------------------------------------------------------
# normalizeMessage — yield SDK-style message dicts
# ---------------------------------------------------------------------------

import time as _time

_tool_progress_last_sent: Dict[str, float] = {}


def normalize_message(message: Message) -> List[Message]:
    """Convert an internal *Message* into a list of SDK-style message dicts.

    Simplified Python port — skips session_id injection (caller responsibility)
    and the full progress throttling logic from the TS source, but preserves
    the same structural transformations.
    """
    msg_type = message.get("type")
    results: List[Message] = []

    if msg_type == "assistant":
        inner = message.get("message", {})
        content = inner.get("content", [])
        if _is_not_empty_message(message):
            results.append(
                {
                    "type": "assistant",
                    "message": inner,
                    "parent_tool_use_id": None,
                    "uuid": message.get("uuid"),
                    "error": message.get("error"),
                }
            )

    elif msg_type == "user":
        results.append(
            {
                "type": "user",
                "message": message.get("message", {}),
                "parent_tool_use_id": None,
                "uuid": message.get("uuid"),
                "timestamp": message.get("timestamp"),
                "is_synthetic": message.get("isMeta") or message.get("isVisibleInTranscriptOnly"),
                "tool_use_result": message.get("toolUseResult"),
            }
        )

    elif msg_type == "progress":
        data = message.get("data", {})
        data_type = data.get("type", "")
        if data_type in ("agent_progress", "skill_progress"):
            inner_msg = data.get("message", {})
            for sub in normalize_message(inner_msg):
                sub["parent_tool_use_id"] = message.get("parentToolUseID")
                results.append(sub)
        elif data_type in ("bash_progress", "powershell_progress"):
            # Throttle: send at most once per TOOL_PROGRESS_THROTTLE_MS
            tracking_key = message.get("parentToolUseID", "")
            now_ms = _time.monotonic() * 1000
            last_sent = _tool_progress_last_sent.get(tracking_key, 0.0)
            if now_ms - last_sent >= TOOL_PROGRESS_THROTTLE_MS:
                if len(_tool_progress_last_sent) >= MAX_TOOL_PROGRESS_TRACKING_ENTRIES:
                    oldest = next(iter(_tool_progress_last_sent))
                    del _tool_progress_last_sent[oldest]
                _tool_progress_last_sent[tracking_key] = now_ms
                tool_name = "Bash" if data_type == "bash_progress" else "PowerShell"
                results.append(
                    {
                        "type": "tool_progress",
                        "tool_use_id": message.get("toolUseID"),
                        "tool_name": tool_name,
                        "parent_tool_use_id": message.get("parentToolUseID"),
                        "elapsed_time_seconds": data.get("elapsedTimeSeconds"),
                        "task_id": data.get("taskId"),
                        "uuid": message.get("uuid"),
                    }
                )

    return results


def _is_not_empty_message(message: Message) -> bool:
    """Return True when *message* has non-empty content (simplified check)."""
    if message.get("type") != "assistant":
        return True
    inner = message.get("message", {})
    content = inner.get("content", [])
    if not isinstance(content, list):
        return bool(content)
    return any(
        isinstance(b, dict) and b.get("type") in ("text", "thinking", "redacted_thinking")
        for b in content
    )


# ---------------------------------------------------------------------------
# inject_tool_results
# ---------------------------------------------------------------------------


def inject_tool_results(
    messages: List[Message],
    tool_results: List[Dict[str, Any]],
) -> List[Message]:
    """Append a ``user`` message containing *tool_results* to *messages*.

    Returns a new list (does not mutate the input).
    """
    if not tool_results:
        return messages
    user_msg: Message = {
        "type": "user",
        "message": {
            "role": "user",
            "content": tool_results,
        },
    }
    return messages + [user_msg]


# ---------------------------------------------------------------------------
# run_tools
# ---------------------------------------------------------------------------


async def run_tools(
    tool_use_blocks: List[Dict[str, Any]],
    tools: Tools,
    *,
    on_result: Optional[Callable[[Message], None]] = None,
) -> List[Dict[str, Any]]:
    """Execute a list of ``tool_use`` blocks and return the ``tool_result`` list.

    Each entry in *tool_use_blocks* must have ``"id"``, ``"name"``, and
    ``"input"`` fields.  Results are executed **concurrently**.

    Parameters
    ----------
    tool_use_blocks:
        List of tool_use content blocks from an assistant message.
    tools:
        Mapping of tool name → async callable.
    on_result:
        Optional callback invoked with each completed tool result message.
    """
    async def _call_one(block: Dict[str, Any]) -> Dict[str, Any]:
        tool_use_id: str = block.get("id", "")
        name: str = block.get("name", "")
        tool_input: Dict[str, Any] = block.get("input", {})

        handler = tools.get(name)
        if handler is None:
            content = f"Unknown tool: {name}"
            is_error = True
        else:
            try:
                raw = await handler(name, tool_input, tool_use_id)
                # Normalise result: accept str, dict, or list
                if isinstance(raw, str):
                    content = raw
                elif isinstance(raw, (list, dict)):
                    content = raw
                else:
                    content = str(raw)
                is_error = False
            except Exception as exc:
                content = f"Tool error: {exc}"
                is_error = True

        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": is_error,
        }

    results = await asyncio.gather(*[_call_one(b) for b in tool_use_blocks])
    return list(results)


# ---------------------------------------------------------------------------
# handle_tool_calls
# ---------------------------------------------------------------------------


async def handle_tool_calls(
    response: Dict[str, Any],
    tools: Tools,
    messages: List[Message],
    *,
    on_update: Optional[Callable[[Message], None]] = None,
) -> Tuple[List[Message], List[Dict[str, Any]]]:
    """Extract and execute tool_use blocks from an LLM *response*.

    Parameters
    ----------
    response:
        A raw LLM response dict (``{"content": [...], "stop_reason": ...}``).
    tools:
        Mapping of tool name → async callable.
    messages:
        Current conversation history (not mutated).
    on_update:
        Optional callback invoked with each result message.

    Returns
    -------
    (updated_messages, tool_results)
        *updated_messages* is *messages* with the assistant turn and tool
        results appended; *tool_results* is the raw list of tool_result blocks.
    """
    content = response.get("content", [])
    tool_use_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]

    if not tool_use_blocks:
        return messages, []

    # Build assistant message
    assistant_msg: Message = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": content,
        },
    }
    updated = messages + [assistant_msg]

    tool_results = await run_tools(tool_use_blocks, tools, on_result=on_update)

    updated = inject_tool_results(updated, tool_results)

    if on_update:
        for tr in tool_results:
            on_update(
                {
                    "type": "user",
                    "message": {"role": "user", "content": [tr]},
                }
            )

    return updated, tool_results


# ---------------------------------------------------------------------------
# extractReadFilesFromMessages  (simplified port)
# ---------------------------------------------------------------------------

_FILE_UNCHANGED_STUB = "(file unchanged)"
_SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>")
_LINE_NUM_RE = re.compile(r"^\s*\d+\t")


def _strip_line_number_prefix(line: str) -> str:
    return _LINE_NUM_RE.sub("", line)


def extract_read_files_from_messages(
    messages: List[Message],
    cwd: str,
    *,
    file_read_tool_name: str = "Read",
    file_write_tool_name: str = "Write",
    file_edit_tool_name: str = "Edit",
) -> Dict[str, Dict[str, Any]]:
    """Build a cache of ``file_path → {content, timestamp}`` from message history.

    Returns a dict mapping absolute file paths to their most recently seen
    contents (from Read/Write/Edit tool results in the conversation).
    """
    import os

    def _expand(path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(cwd, path))

    # First pass: collect tool_use IDs
    file_read_ids: Dict[str, str] = {}  # id -> abs_path
    file_write_ids: Dict[str, Dict[str, str]] = {}  # id -> {filePath, content}
    file_edit_ids: Dict[str, str] = {}  # id -> abs_path

    for msg in messages:
        if msg.get("type") != "assistant":
            continue
        inner = msg.get("message", {})
        content = inner.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            inp = block.get("input", {}) or {}
            bid = block.get("id", "")
            if name == file_read_tool_name:
                fp = inp.get("file_path")
                if (
                    fp
                    and inp.get("offset") is None
                    and inp.get("limit") is None
                ):
                    file_read_ids[bid] = _expand(fp)
            elif name == file_write_tool_name:
                fp = inp.get("file_path")
                c = inp.get("content")
                if fp and c is not None:
                    file_write_ids[bid] = {"filePath": _expand(fp), "content": c}
            elif name == file_edit_tool_name:
                fp = inp.get("file_path")
                if fp:
                    file_edit_ids[bid] = _expand(fp)

    # Second pass: find corresponding tool_result blocks
    cache: Dict[str, Dict[str, Any]] = {}

    for msg in messages:
        if msg.get("type") != "user":
            continue
        inner = msg.get("message", {})
        content = inner.get("content", [])
        if not isinstance(content, list):
            continue
        timestamp_str = msg.get("timestamp")
        ts = 0.0
        if timestamp_str:
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(
                    timestamp_str.replace("Z", "+00:00")
                ).timestamp()
            except Exception:
                pass

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tid = block.get("tool_use_id", "")

            # Handle Read tool results
            read_path = file_read_ids.get(tid)
            if read_path and isinstance(block.get("content"), str):
                c = block["content"]
                if not c.startswith(_FILE_UNCHANGED_STUB):
                    c = _SYSTEM_REMINDER_RE.sub("", c)
                    c = "\n".join(_strip_line_number_prefix(l) for l in c.split("\n")).strip()
                    cache[read_path] = {"content": c, "timestamp": ts}

            # Handle Write tool results
            write_data = file_write_ids.get(tid)
            if write_data:
                cache[write_data["filePath"]] = {
                    "content": write_data["content"],
                    "timestamp": ts,
                }

            # Handle Edit tool results — read current disk state
            edit_path = file_edit_ids.get(tid)
            if edit_path and not block.get("is_error"):
                try:
                    disk_mtime = os.path.getmtime(edit_path)
                    with open(edit_path, "r", encoding="utf-8") as fh:
                        disk_content = fh.read()
                    cache[edit_path] = {"content": disk_content, "timestamp": disk_mtime}
                except Exception:
                    pass

    return cache


# ---------------------------------------------------------------------------
# extractBashToolsFromMessages
# ---------------------------------------------------------------------------

_STRIPPED_COMMANDS: Set[str] = {"sudo"}


def _extract_cli_name(command: Optional[str]) -> Optional[str]:
    """Extract the actual CLI name from a bash command string."""
    if not command:
        return None
    tokens = command.strip().split()
    for token in tokens:
        if re.match(r"^[A-Za-z_]\w*=", token):
            continue
        if token in _STRIPPED_COMMANDS:
            continue
        return token
    return None


def extract_bash_tools_from_messages(
    messages: List[Message],
    bash_tool_name: str = "Bash",
) -> Set[str]:
    """Extract the top-level CLI tools used in BashTool calls from message history."""
    tools_found: Set[str] = set()
    for msg in messages:
        if msg.get("type") != "assistant":
            continue
        content = msg.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == bash_tool_name
            ):
                inp = block.get("input", {})
                cmd = inp.get("command") if isinstance(inp, dict) else None
                name = _extract_cli_name(cmd if isinstance(cmd, str) else None)
                if name:
                    tools_found.add(name)
    return tools_found
