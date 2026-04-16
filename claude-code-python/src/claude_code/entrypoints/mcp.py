"""
MCP Server entrypoint for Claude Code.

Provides `start_mcp_server()` which launches a stdio MCP server that
exposes all Claude Code tools over the Model Context Protocol.

Corresponds to mcp.ts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# Type stubs (mirrors mcp.ts local types)
# ============================================================================

ToolInput = Dict[str, Any]
ToolOutput = Dict[str, Any]


class McpToolResult:
    """Mirrors CallToolResult from @modelcontextprotocol/sdk/types.js"""

    def __init__(
        self,
        content: List[Dict[str, Any]],
        is_error: bool = False,
    ) -> None:
        self.content = content
        self.is_error = is_error


class McpTool:
    """Mirrors the Tool interface from @modelcontextprotocol/sdk/types.js"""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema


# ============================================================================
# MCP Server
# ============================================================================

MCP_SERVER_NAME = "claude/tengu"


async def start_mcp_server(
    cwd: str,
    debug: bool = False,
    verbose: bool = False,
) -> None:
    """
    Start the Claude Code MCP server on stdio.

    Mirrors the TypeScript `startMCPServer` function:
    - Creates an MCP server with all Claude Code tools exposed
    - Handles ListTools and CallTool requests over stdin/stdout
    - Uses a size-limited file state cache (100 files, 25 MB)

    Args:
        cwd:     Working directory for tool execution.
        debug:   Enable debug logging.
        verbose: Enable verbose output.

    In this Python port the function stubs out the actual MCP protocol
    handling. A real implementation would wire in the Python tool registry
    and speak the JSON-RPC MCP protocol on stdio.
    """
    if debug or verbose:
        logging.basicConfig(level=logging.DEBUG)

    logger.debug(
        "[mcp] start_mcp_server called: cwd=%s debug=%s verbose=%s",
        cwd, debug, verbose,
    )

    # Stub: The real implementation would:
    # 1. Create a Server with name=MCP_SERVER_NAME and version=<package version>
    # 2. Register a ListTools handler that enumerates all Claude Code tools
    # 3. Register a CallTool handler that dispatches to the correct Python tool
    # 4. Connect a StdioServerTransport and start listening
    raise NotImplementedError(
        "start_mcp_server is not fully implemented in the Python port. "
        "The TypeScript CLI provides the MCP server; run `claude` directly."
    )


# ============================================================================
# Utility helpers (mirrors internal helpers in mcp.ts)
# ============================================================================


def _make_error_result(error: Exception) -> McpToolResult:
    """Format an exception as an MCP error CallToolResult."""
    error_text = str(error).strip() or "Error"
    return McpToolResult(
        content=[{"type": "text", "text": error_text}],
        is_error=True,
    )


def _make_text_result(text: str) -> McpToolResult:
    """Format a plain text string as an MCP success CallToolResult."""
    return McpToolResult(
        content=[{"type": "text", "text": text}],
        is_error=False,
    )


def _make_json_result(data: Any) -> McpToolResult:
    """Serialize `data` to JSON and wrap it in an MCP success CallToolResult."""
    return McpToolResult(
        content=[{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
        is_error=False,
    )
