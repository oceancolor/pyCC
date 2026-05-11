"""WebSearchTool. Ported from WebSearchTool/WebSearchTool.ts"""
from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Union

WEB_SEARCH_TOOL_NAME = "WebSearch"


class SearchHit:
    """A single search result hit."""

    def __init__(self, title: str, url: str) -> None:
        self.title = title
        self.url = url

    def to_dict(self) -> Dict[str, str]:
        return {"title": self.title, "url": self.url}


class SearchResult:
    """Structured search result with tool_use_id and content hits."""

    def __init__(self, tool_use_id: str, content: List[Dict[str, str]]) -> None:
        self.tool_use_id = tool_use_id
        self.content = content

    def to_dict(self) -> Dict[str, Any]:
        return {"tool_use_id": self.tool_use_id, "content": self.content}


class WebSearchOutput:
    """Output of a web search operation."""

    def __init__(
        self,
        query: str,
        results: List[Union[SearchResult, str]],
        duration_seconds: float,
    ) -> None:
        self.query = query
        self.results = results
        self.duration_seconds = duration_seconds


def _is_provider_supported() -> bool:
    """Check if the current API provider supports web search."""
    provider = _get_api_provider()
    return provider in ("firstParty", "vertex", "foundry", "")


def _get_api_provider() -> str:
    """Return the configured API provider name."""
    try:
        import os
        return os.environ.get("ANTHROPIC_API_PROVIDER", "")
    except Exception:
        return ""


class WebSearchTool:
    """Search the web for current information. Ported from WebSearchTool.ts."""

    name = WEB_SEARCH_TOOL_NAME
    search_hint = "search the web for current information"
    max_result_size_chars = 100_000
    should_defer = True
    is_read_only = True
    is_concurrency_safe = True

    def is_enabled(self) -> bool:
        return _is_provider_supported()

    async def description(self, query: str = "") -> str:
        if query:
            return f"Claude wants to search the web for: {query}"
        return "Search the web for current information"

    async def validate_input(
        self,
        query: str,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not query:
            return {"result": False, "message": "Error: Missing query", "error_code": 1}
        if allowed_domains and blocked_domains:
            return {
                "result": False,
                "message": "Error: Cannot specify both allowed_domains and blocked_domains",
                "error_code": 2,
            }
        return {"result": True}

    async def call(
        self,
        query: str,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
        context: Any = None,
    ) -> Dict[str, Any]:
        """Perform a web search.

        In the Python port we expose the schema but rely on the caller to
        integrate with an actual search backend. Returns a stub result when
        no backend is configured.
        """
        start = time.monotonic()

        # Attempt to use a real backend if one is available.
        results: List[Union[Dict[str, Any], str]] = []
        try:
            results = await self._do_search(query, allowed_domains, blocked_domains)
        except NotImplementedError:
            results = [
                f"Web search is not available in this environment. "
                f"Configure a search backend to enable web search for query: {query}"
            ]
        except Exception as exc:
            results = [f"Web search error: {exc}"]

        duration = time.monotonic() - start
        return {
            "query": query,
            "results": results,
            "duration_seconds": duration,
        }

    async def _do_search(
        self,
        query: str,
        allowed_domains: Optional[List[str]],
        blocked_domains: Optional[List[str]],
    ) -> List[Union[Dict[str, Any], str]]:
        """Override in a subclass to provide a real search backend."""
        raise NotImplementedError("No search backend configured")

    def map_tool_result(self, output: Dict[str, Any], tool_use_id: str) -> Dict[str, Any]:
        query = output.get("query", "")
        results = output.get("results") or []
        formatted = f'Web search results for query: "{query}"\n\n'

        for result in results:
            if result is None:
                continue
            if isinstance(result, str):
                formatted += result + "\n\n"
            elif isinstance(result, dict):
                content = result.get("content", [])
                if content:
                    import json
                    formatted += f"Links: {json.dumps(content)}\n\n"
                else:
                    formatted += "No links found.\n\n"

        formatted += (
            "\nREMINDER: You MUST include the sources above in your response to the user "
            "using markdown hyperlinks."
        )

        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": formatted.strip(),
        }
