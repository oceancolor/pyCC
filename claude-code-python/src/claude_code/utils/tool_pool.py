"""
Tool pool: merge/filter tool lists, coordinator mode filtering.
Ported from toolPool.ts
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, List, Optional

if TYPE_CHECKING:
    from claude_code.Tool import Tool, Tools, ToolPermissionContext

# PR activity subscription tool suffixes
PR_ACTIVITY_TOOL_SUFFIXES = [
    "subscribe_pr_activity",
    "unsubscribe_pr_activity",
]


def is_pr_activity_subscription_tool(name: str) -> bool:
    """Check if tool name ends with a PR activity subscription suffix."""
    return any(name.endswith(suffix) for suffix in PR_ACTIVITY_TOOL_SUFFIXES)


def is_mcp_tool(tool: "Tool") -> bool:
    """Check if a tool is an MCP tool (has ':' in name)."""
    return ":" in getattr(tool, "name", "")


def apply_coordinator_tool_filter(
    tools: "Tools",
    allowed_tools: Optional[set] = None,
) -> "Tools":
    """Filter tools to coordinator-mode-allowed set."""
    if allowed_tools is None:
        # Default: only PR activity tools pass through
        return [t for t in tools if is_pr_activity_subscription_tool(t.name)]
    return [
        t for t in tools
        if t.name in allowed_tools or is_pr_activity_subscription_tool(t.name)
    ]


def merge_and_filter_tools(
    initial_tools: "Tools",
    assembled: "Tools",
    mode: str,
    coordinator_mode: bool = False,
    coordinator_allowed_tools: Optional[set] = None,
) -> "Tools":
    """
    Merge tool pools and apply coordinator mode filtering.

    - initial_tools take precedence in deduplication
    - Built-in tools stay as a prefix (cache stability)
    - MCP tools sorted after built-ins
    """
    # Deduplicate by name, initial_tools win
    seen: dict[str, "Tool"] = {}
    for t in (*initial_tools, *assembled):
        if t.name not in seen:
            seen[t.name] = t

    all_tools = list(seen.values())

    # Partition: built-ins first, MCP after
    mcp = [t for t in all_tools if is_mcp_tool(t)]
    built_in = [t for t in all_tools if not is_mcp_tool(t)]

    mcp.sort(key=lambda t: t.name)
    built_in.sort(key=lambda t: t.name)

    tools = [*built_in, *mcp]

    if coordinator_mode:
        return apply_coordinator_tool_filter(tools, coordinator_allowed_tools)

    return tools
