"""WebSearchTool. Ported from WebSearchTool/."""
from __future__ import annotations
from typing import Any, List, Optional

WEB_SEARCH_TOOL_NAME = "WebSearch"


class WebSearchTool:
    name = WEB_SEARCH_TOOL_NAME
    description = "Search the web for information."
    is_read_only = True

    async def call(self, query: str, context: Any = None) -> dict:
        return {"type": "stub", "query": query,
                "note": "WebSearch requires external API keys. Configure SEARCH_API_KEY."}
