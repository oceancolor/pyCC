"""ToolSearch tool. Ported from ToolSearchTool."""
from __future__ import annotations
import re
from typing import Any, List, Optional

TOOL_SEARCH_TOOL_NAME = "ToolSearch"
DESCRIPTION = "Search for available deferred tools by keyword or select by name"


class ToolSearchTool:
    name = TOOL_SEARCH_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords or 'select:<tool_name>'"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"]
            }
        }

    async def call(self, query: str, max_results: int = 5,
                   deferred_tools: List[Any] = None, **kwargs: Any) -> dict:
        if not deferred_tools:
            return {"matches": [], "query": query, "total_deferred_tools": 0}

        if query.startswith("select:"):
            tool_name = query[7:].strip()
            matches = [t.name for t in deferred_tools if t.name == tool_name]
        else:
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            matches = [t.name for t in deferred_tools
                       if pattern.search(t.name) or pattern.search(getattr(t, "search_hint", ""))]

        return {
            "matches": matches[:max_results],
            "query": query,
            "total_deferred_tools": len(deferred_tools),
        }
