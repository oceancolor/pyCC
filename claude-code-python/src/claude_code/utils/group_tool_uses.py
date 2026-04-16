"""
group_tool_uses.py - Python port of groupToolUses.ts
Source: claude-code-analysis/claude-code-source/utils/groupToolUses.ts

Core functionality:
- Groups tool_use and tool_result messages for rendering
- Only groups 2+ tools of the same type from the same assistant message
- Attaches corresponding tool_results to grouped messages
- Verbose mode: skip grouping so messages render at original positions
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Message type aliases (mirrors the TypeScript message types)
# ---------------------------------------------------------------------------
# We use plain dicts with a 'type' key to stay framework-agnostic in Python.
# Tools are represented as dicts with at minimum {'name': str, 'render_grouped_tool_use': bool}.

Message = Dict[str, Any]
Tool = Dict[str, Any]
Tools = List[Tool]


# ---------------------------------------------------------------------------
# Grouping cache (WeakRef-based equivalent using id → set mapping)
# Note: Python dicts are not WeakMap; we use a simple dict keyed by id.
# Since Tools lists are replaced rather than mutated, stale entries are
# naturally evicted when the list is garbage-collected via gc.
# ---------------------------------------------------------------------------

_GROUPING_CACHE: Dict[int, Set[str]] = {}


def get_tools_with_grouping(tools: Tools) -> Set[str]:
    """
    Return the set of tool names that support grouped rendering.
    Cached by the identity of the tools list.
    """
    key = id(tools)
    cached = _GROUPING_CACHE.get(key)
    if cached is None:
        cached = {t["name"] for t in tools if t.get("render_grouped_tool_use")}
        _GROUPING_CACHE[key] = cached
    return cached


# ---------------------------------------------------------------------------
# Helper: extract tool_use info from an assistant message
# ---------------------------------------------------------------------------

def get_tool_use_info(msg: Message) -> Optional[Dict[str, str]]:
    """
    If msg is an assistant message whose first content block is a tool_use,
    returns {'message_id', 'tool_use_id', 'tool_name'}.
    Otherwise returns None.
    """
    if msg.get("type") != "assistant":
        return None
    message = msg.get("message", {})
    content = message.get("content", [])
    if not content:
        return None
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "tool_use":
        return None
    return {
        "message_id": message.get("id", ""),
        "tool_use_id": first.get("id", ""),
        "tool_name": first.get("name", ""),
    }


# ---------------------------------------------------------------------------
# Grouping result
# ---------------------------------------------------------------------------

@dataclass
class GroupedToolUseMessage:
    """
    Represents a group of tool_use messages of the same type from the same
    assistant response, along with their corresponding tool_results.

    Mirrors the TypeScript GroupedToolUseMessage type.
    """
    type: str = "grouped_tool_use"
    tool_name: str = ""
    messages: List[Message] = field(default_factory=list)   # assistant messages
    results: List[Message] = field(default_factory=list)    # user messages with tool_result
    display_message: Optional[Message] = None               # first message in group
    uuid: str = ""
    timestamp: Optional[Any] = None
    message_id: str = ""


@dataclass
class GroupingResult:
    messages: List[Any] = field(default_factory=list)  # RenderableMessage (Message | GroupedToolUseMessage)


# ---------------------------------------------------------------------------
# Main grouping function
# ---------------------------------------------------------------------------

def apply_grouping(
    messages: List[Message],
    tools: Tools,
    verbose: bool = False,
) -> GroupingResult:
    """
    Groups tool uses by message.id (same API response) if the tool supports
    grouped rendering.  Only groups 2+ tools of the same type from the same
    message.  Also collects corresponding tool_results and attaches them to
    the grouped message.

    When verbose is True, skips grouping so messages render at original
    positions.

    Args:
        messages: List of normalized messages (dicts with 'type' key).
        tools: List of tool definitions (dicts with 'name' and
               'render_grouped_tool_use' keys).
        verbose: If True, return messages unchanged.

    Returns:
        GroupingResult with the (possibly grouped) message list.
    """
    # Verbose mode: no grouping
    if verbose:
        return GroupingResult(messages=list(messages))

    tools_with_grouping = get_tools_with_grouping(tools)

    # ------------------------------------------------------------------
    # First pass: group tool uses by (message_id + tool_name)
    # ------------------------------------------------------------------
    groups: Dict[str, List[Message]] = {}

    for msg in messages:
        info = get_tool_use_info(msg)
        if info and info["tool_name"] in tools_with_grouping:
            key = f"{info['message_id']}:{info['tool_name']}"
            if key not in groups:
                groups[key] = []
            groups[key].append(msg)

    # Identify valid groups (2+ items) and collect their tool_use_ids
    valid_groups: Dict[str, List[Message]] = {}
    grouped_tool_use_ids: Set[str] = set()

    for key, group in groups.items():
        if len(group) >= 2:
            valid_groups[key] = group
            for msg in group:
                info = get_tool_use_info(msg)
                if info:
                    grouped_tool_use_ids.add(info["tool_use_id"])

    # ------------------------------------------------------------------
    # Collect tool_result messages for grouped tool_uses
    # ------------------------------------------------------------------
    # Map from tool_use_id → user message containing that result
    results_by_tool_use_id: Dict[str, Message] = {}

    for msg in messages:
        if msg.get("type") != "user":
            continue
        message = msg.get("message", {})
        for content_block in message.get("content", []):
            if (
                isinstance(content_block, dict)
                and content_block.get("type") == "tool_result"
                and content_block.get("tool_use_id") in grouped_tool_use_ids
            ):
                results_by_tool_use_id[content_block["tool_use_id"]] = msg

    # ------------------------------------------------------------------
    # Second pass: build output, emitting each group only once
    # ------------------------------------------------------------------
    result: List[Any] = []
    emitted_groups: Set[str] = set()

    for msg in messages:
        info = get_tool_use_info(msg)

        if info:
            key = f"{info['message_id']}:{info['tool_name']}"
            group = valid_groups.get(key)

            if group:
                if key not in emitted_groups:
                    emitted_groups.add(key)
                    first_msg = group[0]

                    # Collect results for this group
                    group_results: List[Message] = []
                    for assistant_msg in group:
                        a_message = assistant_msg.get("message", {})
                        a_content = a_message.get("content", [])
                        if a_content:
                            tool_use_id = a_content[0].get("id", "")
                            result_msg = results_by_tool_use_id.get(tool_use_id)
                            if result_msg is not None:
                                group_results.append(result_msg)

                    grouped: GroupedToolUseMessage = GroupedToolUseMessage(
                        type="grouped_tool_use",
                        tool_name=info["tool_name"],
                        messages=list(group),
                        results=group_results,
                        display_message=first_msg,
                        uuid=f"grouped-{first_msg.get('uuid', '')}",
                        timestamp=first_msg.get("timestamp"),
                        message_id=info["message_id"],
                    )
                    result.append(grouped)
                continue  # Skip individual messages that were grouped

        # Skip user messages whose tool_results are ALL grouped
        if msg.get("type") == "user":
            message = msg.get("message", {})
            tool_results = [
                c for c in message.get("content", [])
                if isinstance(c, dict) and c.get("type") == "tool_result"
            ]
            if tool_results:
                all_grouped = all(
                    tr.get("tool_use_id") in grouped_tool_use_ids
                    for tr in tool_results
                )
                if all_grouped:
                    continue

        result.append(msg)

    return GroupingResult(messages=result)
