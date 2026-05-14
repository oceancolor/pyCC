"""MCPTool alias package (top-level mcp_tool directory)."""
from claude_code.tools.mcp_tool.mcp_tool import MCPTool
from claude_code.tools.mcp_tool.classify_for_collapse import classify_mcp_tool_for_collapse

__all__ = ["MCPTool", "classify_mcp_tool_for_collapse"]
