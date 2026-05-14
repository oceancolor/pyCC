"""
WebSearch tool stub
原始 TS: src/tools/WebSearchTool/WebSearchTool.ts

Uses Anthropic's built-in web search capability.
TODO: Full implementation with API beta feature support.
"""
from __future__ import annotations

from typing import Any, Optional

from claude_code.constants.tools import WEB_SEARCH_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext


class WebSearchTool(Tool):
    """
    Web search via Anthropic's built-in search capability.
    原始 TS: src/tools/WebSearchTool/WebSearchTool.ts
    TODO: Full implementation using Anthropic beta web_search_20250305
    """

    name = WEB_SEARCH_TOOL_NAME
    search_hint = "search the web for information"
    max_result_size_chars = 200_000

    async def description(self) -> str:
        return "Search the web for information using Anthropic's built-in search capability."

    async def prompt(self) -> str:
        return """Search the internet for current information.

Use this when you need to:
- Find up-to-date information
- Research topics you don't know about
- Verify current facts

TODO: This tool requires Anthropic's beta web_search feature and is a stub in the Python port."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to use",
                    "minLength": 2,
                },
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only include results from these domains",
                },
                "blocked_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Never include results from these domains",
                },
            },
            "required": ["query"],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        # Delegate to the concrete subdirectory implementation when available.
        try:
            from claude_code.tools.web_search_tool.web_search_tool import WebSearchTool as _WSTImpl  # type: ignore
            impl = _WSTImpl()
            return await impl.call(input_data, context)
        except Exception:
            pass

        # Fallback: let the model know web search requires Anthropic beta.
        query = input_data.get("query", "")
        return {
            "type": "tool_result",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"[WebSearch] query='{query}' — "
                        "Web search requires the Anthropic web_search_20250305 beta "
                        "tool, which is handled natively by the Claude API. "
                        "Consider using WebFetchTool to retrieve a specific URL instead."
                    ),
                }
            ],
        }
