"""
Tool registry and pool assembly.
Ported from tools.ts (464 lines → core).
"""
from __future__ import annotations
import os
from typing import Any, List, Optional

from claude_code.tools.bash_tool import BashTool
from claude_code.tools.file_edit_tool import FileEditTool
from claude_code.tools.file_read_tool import FileReadTool
from claude_code.tools.file_write_tool import FileWriteTool
from claude_code.tools.glob_tool import GlobTool
from claude_code.tools.grep_tool import GrepTool
from claude_code.tools.notebook_edit_tool import NotebookEditTool
from claude_code.tools.web_fetch_tool import WebFetchTool
from claude_code.tools.web_search_tool import WebSearchTool
from claude_code.tools.todo_write_tool import TodoWriteTool

TOOL_PRESETS = ("default",)

REPL_ONLY_TOOL_NAMES = frozenset([
    "Read", "Write", "Edit", "Glob", "Grep", "Bash", "NotebookEdit", "Agent",
])


def parse_tool_preset(preset: str) -> Optional[str]:
    return preset if preset in TOOL_PRESETS else None


def get_tools_for_default_preset() -> List[str]:
    return [
        "Bash", "Read", "Write", "Edit", "Glob", "Grep",
        "Agent", "WebFetch", "WebSearch", "NotebookEdit", "TodoWrite",
    ]


def get_all_base_tools() -> List[Any]:
    """Return all default built-in tool instances."""
    from claude_code.tools.agent_tool import AgentTool
    from claude_code.tools.synthetic_output_tool import SyntheticOutputTool
    from claude_code.tools.exit_plan_mode_tool import ExitPlanModeTool
    from claude_code.tools.task_stop_tool import TaskStopTool

    tools: List[Any] = [
        AgentTool(),
        BashTool(),
        FileEditTool(),
        FileReadTool(),
        FileWriteTool(),
        GlobTool(),
        GrepTool(),
        NotebookEditTool(),
        WebFetchTool(),
        WebSearchTool(),
        TodoWriteTool(),
        ExitPlanModeTool(),
    ]

    # Add TaskStopTool if available
    try:
        from claude_code.tools.task_stop_tool.task_stop_tool import TaskStopTool
        tools.append(TaskStopTool())
    except ImportError:
        pass

    return tools


def filter_tools_by_deny_rules(
    tools: List[Any],
    permission_context: Any = None,
    deny_tools: Optional[List[str]] = None,
) -> List[Any]:
    """Filter out denied tools."""
    if not deny_tools:
        return tools
    deny_set = set(deny_tools)
    return [t for t in tools if getattr(t, "name", "") not in deny_set]


def get_tools(permission_context: Any = None) -> List[Any]:
    """Get enabled tools filtered by permission context."""
    base = get_all_base_tools()
    base = filter_tools_by_deny_rules(base, permission_context)
    # Filter out tools with isEnabled() == False
    result = []
    for t in base:
        is_enabled = getattr(t, "is_enabled", None)
        if is_enabled is None or (callable(is_enabled) and is_enabled()) or is_enabled is True:
            result.append(t)
    return result


def assemble_tool_pool(
    permission_context: Any = None,
    mcp_tools: Optional[List[Any]] = None,
) -> List[Any]:
    """Combine built-in tools with MCP tools (built-ins take precedence)."""
    built_in = get_tools(permission_context)
    extra = filter_tools_by_deny_rules(mcp_tools or [], permission_context)

    # Deduplicate by name: built-ins win
    seen = {getattr(t, "name", ""): t for t in built_in}
    for t in extra:
        name = getattr(t, "name", "")
        if name and name not in seen:
            seen[name] = t

    # Sort for cache stability (built-ins first, sorted; then MCP sorted)
    built_sorted = sorted(built_in, key=lambda t: getattr(t, "name", ""))
    mcp_sorted = sorted(
        [t for t in extra if getattr(t, "name", "") not in {getattr(x, "name", "") for x in built_in}],
        key=lambda t: getattr(t, "name", "")
    )
    return built_sorted + mcp_sorted


def get_merged_tools(
    permission_context: Any = None,
    mcp_tools: Optional[List[Any]] = None,
) -> List[Any]:
    return get_tools(permission_context) + (mcp_tools or [])
