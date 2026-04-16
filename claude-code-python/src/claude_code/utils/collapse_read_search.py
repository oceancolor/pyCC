"""
collapse_read_search.py — Collapse consecutive read/search tool operations.

Ported from utils/collapseReadSearch.ts (1109 lines).

This module provides functions to group consecutive read/search tool calls
into collapsed summary groups for compact display. Unlike the TS version,
this Python port does not depend on React/Ink UI — it operates purely on
message data structures.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

from claude_code.constants.tools import (
    BASH_TOOL_NAME,
    FILE_EDIT_TOOL_NAME,
    FILE_READ_TOOL_NAME,
    FILE_WRITE_TOOL_NAME,
    GLOB_TOOL_NAME,
    GREP_TOOL_NAME,
    REPL_TOOL_NAME,
    TOOL_SEARCH_TOOL_NAME,
)
from claude_code.utils.memory_file_detection import (
    is_auto_managed_memory_file,
    is_auto_managed_memory_pattern,
    is_memory_directory,
    is_shell_command_targeting_memory,
)

# ---------------------------------------------------------------------------
# Feature flags (simplified — no bun:bundle)
# ---------------------------------------------------------------------------

import os

def _feature(name: str) -> bool:
    """Check if a feature flag is enabled via environment variable."""
    return os.environ.get(f"CLAUDE_FEATURE_{name}", "").lower() in ("1", "true", "yes")


def _is_fullscreen_env_enabled() -> bool:
    """Check if fullscreen/tmux mode is enabled."""
    try:
        from claude_code.utils.fullscreen import is_fullscreen_env_enabled
        return is_fullscreen_env_enabled()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_HINT_CHARS = 300

# Tool names for categorization
LIST_TOOL_NAMES: frozenset = frozenset({"ls", "tree", "du"})


# ---------------------------------------------------------------------------
# Public TypedDicts / dataclasses
# ---------------------------------------------------------------------------

class SearchOrReadResult(TypedDict, total=False):
    """Result of checking if a tool use is a search or read operation."""
    isCollapsible: bool
    isSearch: bool
    isRead: bool
    isList: bool
    isREPL: bool
    isMemoryWrite: bool
    isAbsorbedSilently: bool
    mcpServerName: Optional[str]
    isBash: Optional[bool]


class SearchOrReadInfo(TypedDict, total=False):
    """Simplified info for collapsed group processing."""
    isSearch: bool
    isRead: bool
    isList: bool
    isREPL: bool
    isMemoryWrite: bool
    isAbsorbedSilently: bool
    mcpServerName: Optional[str]
    isBash: Optional[bool]


@dataclass
class CollapsedReadSearchGroup:
    """A collapsed group of consecutive read/search tool uses."""
    type: str = "collapsed_read_search"
    search_count: int = 0
    read_count: int = 0
    list_count: int = 0
    repl_count: int = 0
    memory_search_count: int = 0
    memory_read_count: int = 0
    memory_write_count: int = 0
    read_file_paths: List[str] = field(default_factory=list)
    search_args: List[str] = field(default_factory=list)
    latest_display_hint: Optional[str] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    display_message: Optional[Dict[str, Any]] = None
    uuid: Optional[str] = None
    timestamp: Optional[Any] = None
    mcp_call_count: Optional[int] = None
    mcp_server_names: Optional[List[str]] = None
    bash_count: Optional[int] = None
    git_op_bash_count: Optional[int] = None
    hook_total_ms: int = 0
    hook_count: int = 0
    hook_infos: List[Dict[str, Any]] = field(default_factory=list)
    relevant_memories: Optional[List[Dict[str, Any]]] = None
    # Team memory (optional)
    team_memory_search_count: Optional[int] = None
    team_memory_read_count: Optional[int] = None
    team_memory_write_count: Optional[int] = None


# ---------------------------------------------------------------------------
# Internal GroupAccumulator
# ---------------------------------------------------------------------------

@dataclass
class _GroupAccumulator:
    messages: List[Dict[str, Any]] = field(default_factory=list)
    search_count: int = 0
    read_file_paths: Set[str] = field(default_factory=set)
    read_operation_count: int = 0
    list_count: int = 0
    tool_use_ids: Set[str] = field(default_factory=set)
    memory_search_count: int = 0
    memory_read_file_paths: Set[str] = field(default_factory=set)
    memory_write_count: int = 0
    non_mem_search_args: List[str] = field(default_factory=list)
    latest_display_hint: Optional[str] = None
    mcp_call_count: int = 0
    mcp_server_names: Set[str] = field(default_factory=set)
    bash_count: int = 0
    bash_commands: Dict[str, str] = field(default_factory=dict)
    hook_total_ms: int = 0
    hook_count: int = 0
    hook_infos: List[Dict[str, Any]] = field(default_factory=list)
    relevant_memories: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Helper: path utilities
# ---------------------------------------------------------------------------

def _get_file_path_from_tool_input(tool_input: Any) -> Optional[str]:
    """Extract primary file/directory path from a tool_use input."""
    if not isinstance(tool_input, dict):
        return None
    return tool_input.get("file_path") or tool_input.get("path")


def _get_display_path(file_path: str) -> str:
    """Return a short display path (basename or last 2 components)."""
    try:
        from claude_code.utils.file import get_display_path  # type: ignore
        return get_display_path(file_path)
    except Exception:
        # Fallback: use last two path components
        parts = file_path.replace("\\", "/").rstrip("/").split("/")
        if len(parts) <= 2:
            return file_path
        return "/".join(parts[-2:])


def _command_as_hint(command: str) -> str:
    """Format a bash command for the hint display, capped at MAX_HINT_CHARS."""
    cleaned = "$ " + "\n".join(
        line for line in (
            re.sub(r"\s+", " ", l).strip()
            for l in command.split("\n")
        )
        if line
    )
    if len(cleaned) > MAX_HINT_CHARS:
        return cleaned[:MAX_HINT_CHARS - 1] + "…"
    return cleaned


# ---------------------------------------------------------------------------
# Memory search/write detection
# ---------------------------------------------------------------------------

def _is_memory_search(tool_input: Any) -> bool:
    """Check if a search tool targets memory files."""
    if not isinstance(tool_input, dict):
        return False
    path = tool_input.get("path")
    if path and (is_auto_managed_memory_file(path) or is_memory_directory(path)):
        return True
    glob = tool_input.get("glob")
    if glob and is_auto_managed_memory_pattern(glob):
        return True
    command = tool_input.get("command")
    if command and is_shell_command_targeting_memory(command):
        return True
    return False


def _is_memory_write_or_edit(tool_name: str, tool_input: Any) -> bool:
    """Check if a Write/Edit tool targets a memory file."""
    if tool_name not in (FILE_WRITE_TOOL_NAME, FILE_EDIT_TOOL_NAME):
        return False
    file_path = _get_file_path_from_tool_input(tool_input)
    return file_path is not None and is_auto_managed_memory_file(file_path)


# ---------------------------------------------------------------------------
# Tool classification
# ---------------------------------------------------------------------------

def _classify_tool(tool_name: str, tool_input: Any) -> Tuple[bool, bool, bool, bool]:
    """
    Classify a tool use as (is_search, is_read, is_list, is_bash_only).

    Returns (is_search, is_read, is_list, is_bash_command).
    Bash commands that read files (cat, grep, etc.) count as reads.
    """
    if tool_name == GREP_TOOL_NAME:
        return True, False, False, False
    if tool_name == GLOB_TOOL_NAME:
        return False, False, True, False  # glob = listing
    if tool_name == FILE_READ_TOOL_NAME:
        return False, True, False, False
    if tool_name == BASH_TOOL_NAME:
        if not isinstance(tool_input, dict):
            return False, False, False, True
        command = tool_input.get("command", "")
        stripped = command.strip()
        # Detect grep/rg/ag search commands
        if re.match(r"(grep|rg|ag|ack)\b", stripped):
            return True, False, False, False
        # Detect cat/head/tail/less/more/bat (read operations)
        if re.match(r"(cat|head|tail|less|more|bat)\b", stripped):
            return False, True, False, False
        # Detect ls/tree/find/du (listing)
        if re.match(r"(ls|tree|find|du)\b", stripped):
            return False, False, True, False
        return False, False, False, True
    return False, False, False, False


# ---------------------------------------------------------------------------
# Core public API
# ---------------------------------------------------------------------------

def get_tool_search_or_read_info(
    tool_name: str,
    tool_input: Any,
    tools: Any = None,
) -> SearchOrReadResult:
    """
    Check if a tool is a search/read operation.

    Returns a SearchOrReadResult dict with classification flags.
    Also treats Write/Edit of memory files as collapsible.

    Args:
        tool_name: Name of the tool being called.
        tool_input: Input dict for the tool call.
        tools: Optional tools registry (not used in Python port — classifications
               are resolved directly from tool_name).
    """
    # REPL is absorbed silently
    if tool_name == REPL_TOOL_NAME:
        return SearchOrReadResult(
            isCollapsible=True,
            isSearch=False,
            isRead=False,
            isList=False,
            isREPL=True,
            isMemoryWrite=False,
            isAbsorbedSilently=True,
        )

    # Memory file writes/edits are collapsible
    if _is_memory_write_or_edit(tool_name, tool_input):
        return SearchOrReadResult(
            isCollapsible=True,
            isSearch=False,
            isRead=False,
            isList=False,
            isREPL=False,
            isMemoryWrite=True,
            isAbsorbedSilently=False,
        )

    # Meta-operations absorbed silently: ToolSearch
    if tool_name == TOOL_SEARCH_TOOL_NAME and _is_fullscreen_env_enabled():
        return SearchOrReadResult(
            isCollapsible=True,
            isSearch=False,
            isRead=False,
            isList=False,
            isREPL=False,
            isMemoryWrite=False,
            isAbsorbedSilently=True,
        )

    # Classify the tool
    is_search, is_read, is_list, is_bash_only = _classify_tool(tool_name, tool_input)
    is_collapsible = is_search or is_read or is_list

    # Under fullscreen mode, non-search/read Bash commands are also collapsible
    fullscreen = _is_fullscreen_env_enabled()
    if fullscreen and tool_name == BASH_TOOL_NAME and not is_collapsible:
        return SearchOrReadResult(
            isCollapsible=True,
            isSearch=False,
            isRead=False,
            isList=False,
            isREPL=False,
            isMemoryWrite=False,
            isAbsorbedSilently=False,
            isBash=True,
        )

    if not is_collapsible:
        return SearchOrReadResult(
            isCollapsible=False,
            isSearch=False,
            isRead=False,
            isList=False,
            isREPL=False,
            isMemoryWrite=False,
            isAbsorbedSilently=False,
        )

    return SearchOrReadResult(
        isCollapsible=True,
        isSearch=is_search,
        isRead=is_read,
        isList=is_list,
        isREPL=False,
        isMemoryWrite=False,
        isAbsorbedSilently=False,
        isBash=False,
    )


def get_search_or_read_from_content(
    content: Optional[Dict[str, Any]],
    tools: Any = None,
) -> Optional[SearchOrReadInfo]:
    """
    Check if a tool_use content block is a search/read operation.

    Returns SearchOrReadInfo if collapsible, None otherwise.

    Args:
        content: A content block dict (e.g. {"type": "tool_use", "name": ..., "input": ...}).
        tools: Optional tools registry (unused in Python port).
    """
    if not content or content.get("type") != "tool_use":
        return None
    name = content.get("name")
    if not name:
        return None
    info = get_tool_search_or_read_info(name, content.get("input"), tools)
    if info.get("isCollapsible") or info.get("isREPL"):
        return SearchOrReadInfo(
            isSearch=info.get("isSearch", False),
            isRead=info.get("isRead", False),
            isList=info.get("isList", False),
            isREPL=info.get("isREPL", False),
            isMemoryWrite=info.get("isMemoryWrite", False),
            isAbsorbedSilently=info.get("isAbsorbedSilently", False),
            mcpServerName=info.get("mcpServerName"),
            isBash=info.get("isBash"),
        )
    return None


def get_tool_use_ids_from_collapsed_group(
    message: CollapsedReadSearchGroup,
) -> List[str]:
    """Get all tool use IDs from a collapsed read/search group."""
    ids: List[str] = []
    for msg in message.messages:
        ids.extend(_get_tool_use_ids_from_message(msg))
    return ids


def has_any_tool_in_progress(
    message: CollapsedReadSearchGroup,
    in_progress_tool_use_ids: Set[str],
) -> bool:
    """Check if any tool in a collapsed group is in progress."""
    return any(
        tid in in_progress_tool_use_ids
        for tid in get_tool_use_ids_from_collapsed_group(message)
    )


def get_display_message_from_collapsed(
    message: CollapsedReadSearchGroup,
) -> Optional[Dict[str, Any]]:
    """
    Get the underlying message for display (timestamp/model).

    Returns the first non-grouped message in the collapsed group,
    unwrapping grouped_tool_use wrappers when needed.
    """
    first = message.display_message
    if first is None and message.messages:
        first = message.messages[0]
    if first is None:
        return None
    # Unwrap grouped_tool_use
    if first.get("type") == "grouped_tool_use":
        return first.get("displayMessage") or (
            first.get("messages", [None])[0]
        )
    return first


def collapse_read_search_groups(
    messages: List[Dict[str, Any]],
    tools: Any = None,
) -> List[Dict[str, Any]]:
    """
    Collapse consecutive Read/Search operations into summary groups.

    Rules:
    - Groups consecutive search/read tool uses (Grep, Glob, Read, Bash
      search/read commands)
    - Includes their corresponding tool results in the group
    - Breaks groups when assistant text appears or a non-collapsible tool
      use is encountered

    Args:
        messages: List of RenderableMessage dicts.
        tools: Optional tools registry (unused in Python port).

    Returns:
        List of messages with consecutive read/search groups replaced by
        CollapsedReadSearchGroup dicts.
    """
    result: List[Dict[str, Any]] = []
    current_group = _GroupAccumulator()
    deferred_skippable: List[Dict[str, Any]] = []

    def flush_group() -> None:
        nonlocal current_group, deferred_skippable
        if not current_group.messages:
            return
        collapsed = _create_collapsed_group(current_group)
        result.append(collapsed.__dict__)
        for deferred in deferred_skippable:
            result.append(deferred)
        deferred_skippable = []
        current_group = _GroupAccumulator()

    for msg in messages:
        msg_type = msg.get("type")

        if _is_collapsible_tool_use(msg, tools):
            tool_info = _get_collapsible_tool_info(msg, tools)
            if tool_info is None:
                flush_group()
                result.append(msg)
                continue

            if tool_info.get("isMemoryWrite"):
                count = _count_tool_uses(msg)
                current_group.memory_write_count += count

            elif tool_info.get("isAbsorbedSilently"):
                # Snip/ToolSearch — no count, no summary text
                pass

            elif tool_info.get("mcpServerName"):
                count = _count_tool_uses(msg)
                current_group.mcp_call_count += count
                current_group.mcp_server_names.add(tool_info["mcpServerName"])
                inp = tool_info.get("input") or {}
                if isinstance(inp, dict) and inp.get("query"):
                    current_group.latest_display_hint = f'"{inp["query"]}"'

            elif _is_fullscreen_env_enabled() and tool_info.get("isBash"):
                count = _count_tool_uses(msg)
                current_group.bash_count += count
                inp = tool_info.get("input") or {}
                if isinstance(inp, dict) and inp.get("command"):
                    cmd = inp["command"]
                    current_group.latest_display_hint = _command_as_hint(cmd)
                    for tid in _get_tool_use_ids_from_message(msg):
                        current_group.bash_commands[tid] = cmd

            elif tool_info.get("isList"):
                current_group.list_count += _count_tool_uses(msg)
                inp = tool_info.get("input") or {}
                if isinstance(inp, dict) and inp.get("command"):
                    current_group.latest_display_hint = _command_as_hint(inp["command"])

            elif tool_info.get("isSearch"):
                count = _count_tool_uses(msg)
                current_group.search_count += count
                inp = tool_info.get("input") or {}
                if _is_memory_search(inp):
                    current_group.memory_search_count += count
                else:
                    pattern = inp.get("pattern") if isinstance(inp, dict) else None
                    if pattern:
                        current_group.non_mem_search_args.append(pattern)
                        current_group.latest_display_hint = f'"{pattern}"'

            else:
                # Read operations — track unique file paths
                file_paths = _get_file_paths_from_read_message(msg)
                for fp in file_paths:
                    current_group.read_file_paths.add(fp)
                    if is_auto_managed_memory_file(fp):
                        current_group.memory_read_file_paths.add(fp)
                    else:
                        current_group.latest_display_hint = _get_display_path(fp)
                if not file_paths:
                    current_group.read_operation_count += _count_tool_uses(msg)
                    inp = tool_info.get("input") or {}
                    if isinstance(inp, dict) and inp.get("command"):
                        current_group.latest_display_hint = _command_as_hint(inp["command"])

            # Track tool use IDs
            for tid in _get_tool_use_ids_from_message(msg):
                current_group.tool_use_ids.add(tid)

            current_group.messages.append(msg)

        elif _is_collapsible_tool_result(msg, current_group.tool_use_ids):
            current_group.messages.append(msg)

        elif (
            current_group.messages
            and msg_type == "system"
            and msg.get("subtype") == "stop_hook_summary"
            and msg.get("hookLabel") == "PreToolUse"
        ):
            # Absorb PreToolUse hook summaries
            current_group.hook_count += msg.get("hookCount", 0)
            current_group.hook_total_ms += (
                msg.get("totalDurationMs", 0)
                or sum(h.get("durationMs", 0) for h in msg.get("hookInfos", []))
            )
            current_group.hook_infos.extend(msg.get("hookInfos", []))

        elif (
            current_group.messages
            and msg_type == "attachment"
            and isinstance(msg.get("attachment"), dict)
            and msg["attachment"].get("type") == "relevant_memories"
        ):
            # Absorb auto-injected memory attachments
            if current_group.relevant_memories is None:
                current_group.relevant_memories = []
            current_group.relevant_memories.extend(
                msg["attachment"].get("memories", [])
            )

        elif _should_skip_message(msg):
            if (
                current_group.messages
                and not (
                    msg_type == "attachment"
                    and isinstance(msg.get("attachment"), dict)
                    and msg["attachment"].get("type") == "nested_memory"
                )
            ):
                deferred_skippable.append(msg)
            else:
                result.append(msg)

        elif _is_text_breaker(msg):
            flush_group()
            result.append(msg)

        elif _is_non_collapsible_tool_use(msg, tools):
            flush_group()
            result.append(msg)

        else:
            flush_group()
            result.append(msg)

    flush_group()
    return result


def get_search_read_summary_text(
    search_count: int,
    read_count: int,
    is_active: bool,
    repl_count: int = 0,
    memory_counts: Optional[Dict[str, int]] = None,
    list_count: int = 0,
) -> str:
    """
    Generate a summary text for search/read/REPL counts.

    Args:
        search_count: Number of search operations.
        read_count: Number of read operations.
        is_active: If True, use present tense ("Reading…"); if False, past tense ("Read").
        repl_count: Number of REPL executions.
        memory_counts: Optional dict with memory operation counts.
        list_count: Number of directory-listing operations.

    Returns:
        Summary text like "Searched for 3 patterns, read 2 files".
    """
    parts: List[str] = []

    def _verb(active_cap: str, active_low: str, past_cap: str, past_low: str) -> str:
        if is_active:
            return active_cap if not parts else active_low
        else:
            return past_cap if not parts else past_low

    # Memory operations first
    if memory_counts:
        mem_read = memory_counts.get("memoryReadCount", 0)
        mem_search = memory_counts.get("memorySearchCount", 0)
        mem_write = memory_counts.get("memoryWriteCount", 0)

        if mem_read > 0:
            verb = _verb("Recalling", "recalling", "Recalled", "recalled")
            noun = "memory" if mem_read == 1 else "memories"
            parts.append(f"{verb} {mem_read} {noun}")

        if mem_search > 0:
            verb = _verb("Searching", "searching", "Searched", "searched")
            parts.append(f"{verb} memories")

        if mem_write > 0:
            verb = _verb("Writing", "writing", "Wrote", "wrote")
            noun = "memory" if mem_write == 1 else "memories"
            parts.append(f"{verb} {mem_write} {noun}")

    if search_count > 0:
        verb = _verb("Searching for", "searching for", "Searched for", "searched for")
        noun = "pattern" if search_count == 1 else "patterns"
        parts.append(f"{verb} {search_count} {noun}")

    if read_count > 0:
        verb = _verb("Reading", "reading", "Read", "read")
        noun = "file" if read_count == 1 else "files"
        parts.append(f"{verb} {read_count} {noun}")

    if list_count > 0:
        verb = _verb("Listing", "listing", "Listed", "listed")
        noun = "directory" if list_count == 1 else "directories"
        parts.append(f"{verb} {list_count} {noun}")

    if repl_count > 0:
        verb = "REPL'ing" if is_active else "REPL'd"
        noun = "time" if repl_count == 1 else "times"
        parts.append(f"{verb} {repl_count} {noun}")

    text = ", ".join(parts)
    return f"{text}…" if is_active else text


def summarize_recent_activities(
    activities: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Summarize a list of recent tool activities into a compact description.

    Rolls up trailing consecutive search/read operations using pre-computed
    isSearch/isRead classifications. Falls back to the last activity's
    description for non-collapsible tool uses.

    Args:
        activities: List of activity dicts with optional keys:
            - activityDescription: str
            - isSearch: bool
            - isRead: bool

    Returns:
        A summary string, or None if activities is empty.
    """
    if not activities:
        return None

    # Count trailing search/read activities from the end
    search_count = 0
    read_count = 0
    for activity in reversed(activities):
        if activity.get("isSearch"):
            search_count += 1
        elif activity.get("isRead"):
            read_count += 1
        else:
            break

    collapsible_count = search_count + read_count
    if collapsible_count >= 2:
        return get_search_read_summary_text(search_count, read_count, True)

    # Fall back to most recent activity with a description
    for activity in reversed(activities):
        if activity.get("activityDescription"):
            return activity["activityDescription"]

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_tool_use_ids_from_message(msg: Dict[str, Any]) -> List[str]:
    """Get all tool use IDs from a single message (handles grouped tool uses)."""
    ids: List[str] = []
    msg_type = msg.get("type")

    if msg_type == "assistant":
        content_list = msg.get("message", {}).get("content", [])
        if isinstance(content_list, list) and content_list:
            block = content_list[0]
            if isinstance(block, dict) and block.get("type") == "tool_use":
                bid = block.get("id")
                if bid:
                    ids.append(bid)
        elif isinstance(content_list, str):
            pass  # plain text, no tool_use

    elif msg_type == "grouped_tool_use":
        for sub_msg in msg.get("messages", []):
            sub_content = sub_msg.get("message", {}).get("content", [])
            if isinstance(sub_content, list) and sub_content:
                block = sub_content[0]
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    bid = block.get("id")
                    if bid:
                        ids.append(bid)

    return ids


def _count_tool_uses(msg: Dict[str, Any]) -> int:
    """Count the number of tool uses in a message (handles grouped tool uses)."""
    if msg.get("type") == "grouped_tool_use":
        return len(msg.get("messages", []))
    return 1


def _get_file_paths_from_read_message(msg: Dict[str, Any]) -> List[str]:
    """Extract file paths from read tool inputs in a message."""
    paths: List[str] = []
    msg_type = msg.get("type")

    if msg_type == "assistant":
        content_list = msg.get("message", {}).get("content", [])
        if isinstance(content_list, list) and content_list:
            block = content_list[0]
            if isinstance(block, dict) and block.get("type") == "tool_use":
                inp = block.get("input") or {}
                if isinstance(inp, dict):
                    fp = inp.get("file_path")
                    if fp:
                        paths.append(fp)

    elif msg_type == "grouped_tool_use":
        for sub_msg in msg.get("messages", []):
            sub_content = sub_msg.get("message", {}).get("content", [])
            if isinstance(sub_content, list) and sub_content:
                block = sub_content[0]
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    inp = block.get("input") or {}
                    if isinstance(inp, dict):
                        fp = inp.get("file_path")
                        if fp:
                            paths.append(fp)

    return paths


def _get_collapsible_tool_info(
    msg: Dict[str, Any],
    tools: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    Get the tool name, input, and classification info from a collapsible message.

    Returns None if the message is not a collapsible tool use.
    """
    msg_type = msg.get("type")

    if msg_type == "assistant":
        content_list = msg.get("message", {}).get("content", [])
        if isinstance(content_list, list) and content_list:
            content = content_list[0]
            if isinstance(content, dict) and content.get("type") == "tool_use":
                info = get_search_or_read_from_content(content, tools)
                if info is not None:
                    return {
                        "name": content.get("name"),
                        "input": content.get("input"),
                        **info,
                    }

    elif msg_type == "grouped_tool_use":
        first_content_list = (
            msg.get("messages", [{}])[0].get("message", {}).get("content", [])
            if msg.get("messages") else []
        )
        tool_name = msg.get("toolName")
        if isinstance(first_content_list, list) and first_content_list and tool_name:
            first_block = first_content_list[0]
            synthetic = {"type": "tool_use", "name": tool_name, "input": (
                first_block.get("input") if isinstance(first_block, dict) else None
            )}
            info = get_search_or_read_from_content(synthetic, tools)
            if info is not None and isinstance(first_block, dict):
                return {
                    "name": tool_name,
                    "input": first_block.get("input"),
                    **info,
                }

    return None


def _is_collapsible_tool_use(msg: Dict[str, Any], tools: Any = None) -> bool:
    """Type predicate: check if a message is a collapsible tool use."""
    return _get_collapsible_tool_info(msg, tools) is not None


def _is_collapsible_tool_result(
    msg: Dict[str, Any],
    collapsible_tool_use_ids: Set[str],
) -> bool:
    """
    Type predicate: check if a message is a tool result for collapsible tools.

    Returns True only if ALL tool results in the message are for tracked
    collapsible tools.
    """
    if msg.get("type") != "user":
        return False
    content_list = msg.get("message", {}).get("content", [])
    if not isinstance(content_list, list):
        return False
    tool_results = [
        c for c in content_list
        if isinstance(c, dict) and c.get("type") == "tool_result"
    ]
    return (
        len(tool_results) > 0
        and all(r.get("tool_use_id") in collapsible_tool_use_ids for r in tool_results)
    )


def _is_text_breaker(msg: Dict[str, Any]) -> bool:
    """Check if a message is assistant text that should break a group."""
    if msg.get("type") != "assistant":
        return False
    content_list = msg.get("message", {}).get("content", [])
    if isinstance(content_list, str):
        return bool(content_list.strip())
    if isinstance(content_list, list) and content_list:
        block = content_list[0]
        if isinstance(block, dict) and block.get("type") == "text":
            return bool(block.get("text", "").strip())
    return False


def _is_non_collapsible_tool_use(msg: Dict[str, Any], tools: Any = None) -> bool:
    """Check if a message is a non-collapsible tool use that should break a group."""
    msg_type = msg.get("type")

    if msg_type == "assistant":
        content_list = msg.get("message", {}).get("content", [])
        if isinstance(content_list, list) and content_list:
            block = content_list[0]
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return _get_collapsible_tool_info(msg, tools) is None
    elif msg_type == "grouped_tool_use":
        return _get_collapsible_tool_info(msg, tools) is None
    return False


def _should_skip_message(msg: Dict[str, Any]) -> bool:
    """
    Check if a message should be skipped (not break group, just pass through).

    Includes thinking blocks, redacted thinking, attachments, system messages.
    """
    msg_type = msg.get("type")

    if msg_type == "assistant":
        content_list = msg.get("message", {}).get("content", [])
        if isinstance(content_list, list) and content_list:
            block = content_list[0]
            if isinstance(block, dict) and block.get("type") in ("thinking", "redacted_thinking"):
                return True

    if msg_type == "attachment":
        return True

    if msg_type == "system":
        return True

    return False


def _create_collapsed_group(group: _GroupAccumulator) -> CollapsedReadSearchGroup:
    """Convert a GroupAccumulator into a CollapsedReadSearchGroup."""
    if not group.messages:
        raise ValueError("Cannot create collapsed group from empty accumulator")

    first_msg = group.messages[0]

    # Read count: prefer unique file paths, fall back to operation count
    total_read_count = (
        len(group.read_file_paths)
        if group.read_file_paths
        else group.read_operation_count
    )

    tool_memory_read_count = len(group.memory_read_file_paths)
    memory_read_count = tool_memory_read_count + len(group.relevant_memories or [])

    # Non-memory read file paths
    non_mem_read_file_paths = [
        p for p in group.read_file_paths
        if p not in group.memory_read_file_paths
    ]

    collapsed = CollapsedReadSearchGroup(
        type="collapsed_read_search",
        search_count=max(0, group.search_count - group.memory_search_count),
        read_count=max(0, total_read_count - tool_memory_read_count),
        list_count=group.list_count,
        repl_count=0,
        memory_search_count=group.memory_search_count,
        memory_read_count=memory_read_count,
        memory_write_count=group.memory_write_count,
        read_file_paths=non_mem_read_file_paths,
        search_args=list(group.non_mem_search_args),
        latest_display_hint=group.latest_display_hint,
        messages=list(group.messages),
        display_message=first_msg,
        uuid=f"collapsed-{first_msg.get('uuid', id(first_msg))}",
        timestamp=first_msg.get("timestamp"),
    )

    if group.mcp_call_count > 0:
        collapsed.mcp_call_count = group.mcp_call_count
        collapsed.mcp_server_names = list(group.mcp_server_names)

    if _is_fullscreen_env_enabled() and group.bash_count > 0:
        collapsed.bash_count = group.bash_count
        collapsed.git_op_bash_count = 0

    if group.hook_count > 0:
        collapsed.hook_total_ms = group.hook_total_ms
        collapsed.hook_count = group.hook_count
        collapsed.hook_infos = list(group.hook_infos)

    if group.relevant_memories:
        collapsed.relevant_memories = list(group.relevant_memories)

    return collapsed


# ---------------------------------------------------------------------------
# Backwards-compatible aliases (keep existing callers working)
# ---------------------------------------------------------------------------

def collapse_read_search_messages(
    messages: List[Dict[str, Any]],
    tools: Any = None,
) -> List[Dict[str, Any]]:
    """Alias for collapse_read_search_groups (backwards compatibility)."""
    return collapse_read_search_groups(messages, tools)
