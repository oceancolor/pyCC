"""ToolSearchTool package.

Re-exports ToolSearchTool and its canonical name constant.

ToolSearchTool searches the catalogue of available tools by keyword,
returning matching tool names and descriptions.  Useful when the agent
is unsure which tool to use for a specific task.

Ported from: tools/ToolSearchTool/ (TypeScript)

Usage::

    from claude_code.tools.tool_search_tool import ToolSearchTool, TOOL_SEARCH_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.tool_search_tool.tool_search_tool import ToolSearchTool
from claude_code.tools.tool_search_tool.constants import TOOL_SEARCH_TOOL_NAME

__all__ = [
    "ToolSearchTool",
    "TOOL_SEARCH_TOOL_NAME",
]
