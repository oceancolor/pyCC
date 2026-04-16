"""WebFetchTool. Ported from WebFetchTool/."""
from __future__ import annotations
from typing import Any, Optional

WEB_FETCH_TOOL_NAME = "WebFetch"


class WebFetchTool:
    name = WEB_FETCH_TOOL_NAME
    description = "Fetch and extract content from a URL."
    is_read_only = True

    async def call(self, url: str, prompt: str = "", context: Any = None) -> dict:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "ClaudeCode/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="replace")
            return {"type": "success", "url": url, "content": content[:50_000]}
        except Exception as e:
            return {"type": "error", "error": str(e)}
