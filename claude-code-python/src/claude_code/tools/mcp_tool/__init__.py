"""MCPTool alias package (top-level mcp_tool directory). Ported from MCPTool/"""
from claude_code.tools.mcp_tool.mcp_tool import MCPTool, MCP_TOOL_NAME_PREFIX, make_mcp_tool_name
from claude_code.tools.mcp_tool.classify_for_collapse import classify_mcp_tool_for_collapse

__all__ = [
    "MCPTool",
    "MCP_TOOL_NAME_PREFIX",
    "make_mcp_tool_name",
    "classify_mcp_tool_for_collapse",
]
