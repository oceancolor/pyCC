"""MCPTool prompt constants.

Ported from: tools/MCPTool/prompt.ts

The actual prompt and description for each MCP tool are set dynamically
by the MCP client when the tool is registered at runtime (see
``mcpClient.ts``).  The constants here are intentionally empty strings
that serve as placeholders / default values before the client overrides them.
"""
from __future__ import annotations

#: Runtime-overridden system prompt for the MCP tool.
#: Set by the MCP client when the server tool is registered.
PROMPT: str = ""

#: Runtime-overridden short description for the MCP tool.
#: Set by the MCP client when the server tool is registered.
DESCRIPTION: str = ""

__all__ = ["PROMPT", "DESCRIPTION"]
