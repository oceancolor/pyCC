"""
WebFetch tool implementation
原始 TS: src/tools/WebFetchTool/WebFetchTool.ts

Fetches content from a URL and optionally applies a prompt to it.
"""
from __future__ import annotations

import time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from claude_code.constants.tools import WEB_FETCH_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext, ValidationResult, ValidationResultFail, ValidationResultOk

MAX_MARKDOWN_LENGTH = 200_000
FETCH_TIMEOUT = 30.0


class WebFetchTool(Tool):
    """
    Fetches content from a URL.
    原始 TS: src/tools/WebFetchTool/WebFetchTool.ts
    """

    name = WEB_FETCH_TOOL_NAME
    search_hint = "fetch and extract content from a URL"
    max_result_size_chars = 100_000

    async def description(self) -> str:
        return "Fetches content from a URL and optionally applies a prompt/filter to it."

    async def prompt(self) -> str:
        return """Fetches content from a URL and returns the content.

Usage:
- Provide a URL to fetch its content
- Optionally provide a prompt to filter/extract specific information
- Supports HTTP and HTTPS URLs
- Returns text content (HTML is converted to readable text)

Note: Some sites may block automated requests."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch content from",
                },
                "prompt": {
                    "type": "string",
                    "description": "Optional prompt to apply to the fetched content",
                },
            },
            "required": ["url"],
        }

    async def validate_input(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult:
        url = input_data.get("url", "")
        if not url or not isinstance(url, str):
            return ValidationResultFail(result=False, message="url must be a non-empty string", error_code=1)
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return ValidationResultFail(
                    result=False,
                    message=f"URL scheme must be http or https, got: {parsed.scheme}",
                    error_code=1,
                )
        except Exception as e:
            return ValidationResultFail(result=False, message=f"Invalid URL: {e}", error_code=1)
        return ValidationResultOk()

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        url: str = input_data["url"]
        prompt: Optional[str] = input_data.get("prompt")

        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; ClaudeCode/1.0)",
                        "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
                    },
                )

            duration_ms = (time.monotonic() - start) * 1000
            content_bytes = response.content
            content_text = response.text

            # Try to extract readable text
            content_type = response.headers.get("content-type", "")
            if "html" in content_type:
                content_text = _html_to_text(content_text)

            # Truncate if too long
            if len(content_text) > MAX_MARKDOWN_LENGTH:
                content_text = content_text[:MAX_MARKDOWN_LENGTH] + "\n\n[Content truncated]"

            result = {
                "url": str(response.url),
                "code": response.status_code,
                "code_text": response.reason_phrase or "",
                "bytes": len(content_bytes),
                "duration_ms": duration_ms,
                "result": content_text,
            }

            return {
                "type": "text",
                "text": content_text,
                "metadata": result,
            }

        except httpx.RequestError as e:
            return {
                "type": "text",
                "text": f"Error fetching {url}: {e}",
            }
        except Exception as e:
            return {
                "type": "text",
                "text": f"Unexpected error: {e}",
            }

    def user_facing_name(self, input_data: Optional[dict[str, Any]] = None) -> str:
        if input_data and "url" in input_data:
            try:
                parsed = urlparse(input_data["url"])
                return parsed.hostname or input_data["url"]
            except Exception:
                return input_data["url"]
        return "URL"

    def get_tool_use_summary(self, input_data: dict[str, Any]) -> Optional[str]:
        return input_data.get("url", "")


def _html_to_text(html: str) -> str:
    """
    Convert HTML to readable text.
    Simple regex-based approach (no heavy dependencies).
    TODO: Consider using `html2text` package for better quality.
    """
    import re

    # Remove script and style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace common block elements with newlines
    html = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Remove remaining HTML tags
    html = re.sub(r"<[^>]+>", "", html)
    # Decode common HTML entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Normalize whitespace
    html = re.sub(r"\n{3,}", "\n\n", html)
    html = re.sub(r"[ \t]+", " ", html)
    return html.strip()
