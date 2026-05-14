"""MCP command package.

Provides /mcp command for managing MCP (Model Context Protocol) servers.
Ported from commands/mcp/
"""
from __future__ import annotations

from .index import McpCommand, default, NAME, DESCRIPTION, TYPE
from .mcp import call

__all__ = ["McpCommand", "default", "NAME", "DESCRIPTION", "TYPE", "call"]
