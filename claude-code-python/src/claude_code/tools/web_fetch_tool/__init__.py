"""WebFetchTool package.

Re-exports the WebFetchTool class from its implementation module.

WebFetchTool fetches content from a given URL and processes it using the
language model.  It takes a URL and an optional prompt, retrieves the page
(following redirects), and returns an AI-processed summary or extraction.

The tool uses the Anthropic Files API under the hood when the response is
large, converting HTML to Markdown before sending it to the model to keep
token usage reasonable.

Ported from: tools/WebFetchTool/ (TypeScript)

Usage::

    from claude_code.tools.web_fetch_tool import WebFetchTool
"""
from __future__ import annotations

from claude_code.tools.web_fetch_tool.web_fetch_tool import WebFetchTool

__all__ = ["WebFetchTool"]
