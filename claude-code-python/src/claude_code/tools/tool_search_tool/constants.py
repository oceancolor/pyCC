"""ToolSearchTool constants.

Ported from: tools/ToolSearchTool/constants.ts

Defines the canonical API-level tool name used to identify the
ToolSearch tool in tool-use messages and permission rules.

ToolSearch searches the catalogue of available tools by keyword, returning
matching tool names, descriptions, and usage hints.  It is useful when
the agent is unsure which tool is most appropriate for a given task.

See also
--------
``claude_code.tools.tool_search_tool.tool_search_tool`` : Implementation.
"""
from __future__ import annotations

#: The API-level tool name used to identify the ToolSearch tool.
TOOL_SEARCH_TOOL_NAME: str = "ToolSearch"

__all__ = ["TOOL_SEARCH_TOOL_NAME"]
