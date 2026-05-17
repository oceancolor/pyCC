"""MCPTool prompt constants. Ported from MCPTool/prompt.ts"""
from __future__ import annotations

# Per MCPTool/prompt.ts: actual prompt and description are overridden
# per MCP client at runtime (set in mcpClient.ts when the tool is registered).
PROMPT: str = ""
DESCRIPTION: str = ""

__all__ = ["PROMPT", "DESCRIPTION"]
