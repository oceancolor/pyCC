"""WebSearchTool package.

Re-exports the WebSearchTool class from its implementation module.

WebSearchTool performs a web search using the configured search provider
(Brave Search by default) and returns a list of relevant results including
titles, URLs, and snippets.

The tool requires a valid search API key to be configured in the Claude Code
settings.  Results are returned as structured data so the agent can decide
which URLs to fetch with ``WebFetchTool`` for deeper analysis.

Ported from: tools/WebSearchTool/ (TypeScript)

Usage::

    from claude_code.tools.web_search_tool import WebSearchTool
"""
from __future__ import annotations

from claude_code.tools.web_search_tool.web_search_tool import WebSearchTool

__all__ = ["WebSearchTool"]
