"""WebFetchTool. Ported from WebFetchTool/WebFetchTool.ts."""
from __future__ import annotations

import time
from typing import Any, Optional
from urllib.parse import urlparse

WEB_FETCH_TOOL_NAME = "WebFetch"
MAX_CONTENT_CHARS = 50_000  # Practical truncation limit for the Python port


class WebFetchTool:
    """Fetch a URL and return its content (optionally filtered by a prompt).

    This is a best-effort Python port of WebFetchTool/WebFetchTool.ts.  The TS
    version uses Axios, converts HTML → Markdown via a secondary model call, and
    applies domain-block checks.  The Python port uses ``urllib`` (no extra
    dependencies) and returns raw text/markdown; callers can post-process with
    any LLM they choose.

    Key behaviours mirrored from TS:
    - HTTP URLs are silently upgraded to HTTPS.
    - Returns a structured dict with ``bytes``, ``code``, ``codeText``, ``url``,
      ``result``, and ``durationMs``.
    - On redirect to a different host, reports the redirect URL.
    - Binary content types return an error message.
    - Is read-only and concurrency-safe.
    """

    name = WEB_FETCH_TOOL_NAME
    description = "Fetch and extract content from a URL"
    is_read_only = True
    is_concurrency_safe = True
    should_defer = True
    max_result_size_chars = 100_000

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch content from",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "The prompt to run on the fetched content",
                    },
                },
                "required": ["url", "prompt"],
            },
        }

    async def call(
        self,
        url: str,
        prompt: str = "",
        context: Any = None,
        **kwargs: Any,
    ) -> dict:
        import urllib.error
        import urllib.request

        # Upgrade HTTP → HTTPS (mirrors TS normalisation)
        if url.startswith("http://"):
            url = "https://" + url[7:]

        start_ms = time.time() * 1000

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "ClaudeCode/1.0 (+https://claude.ai)",
                    "Accept": "text/html,text/plain,application/xhtml+xml,*/*;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                final_url: str = resp.url or url
                code: int = resp.status
                code_text: str = resp.reason or str(code)
                content_type: str = resp.headers.get("Content-Type", "")

                # Detect binary content
                if self._is_binary(content_type):
                    return {
                        "bytes": 0,
                        "code": code,
                        "codeText": code_text,
                        "result": f"Binary content type ({content_type}) — cannot display.",
                        "durationMs": time.time() * 1000 - start_ms,
                        "url": final_url,
                    }

                raw: bytes = resp.read()
                text: str = raw.decode("utf-8", errors="replace")

        except urllib.error.HTTPError as exc:
            return {
                "bytes": 0,
                "code": exc.code,
                "codeText": exc.reason or str(exc.code),
                "result": f"HTTP {exc.code}: {exc.reason}",
                "durationMs": time.time() * 1000 - start_ms,
                "url": url,
            }
        except Exception as exc:
            return {
                "bytes": 0,
                "code": 0,
                "codeText": "error",
                "result": f"Fetch error: {exc}",
                "durationMs": time.time() * 1000 - start_ms,
                "url": url,
            }

        # Check for cross-origin redirect
        if final_url != url:
            orig_host = urlparse(url).netloc
            final_host = urlparse(final_url).netloc
            if orig_host != final_host:
                return {
                    "bytes": len(raw),
                    "code": code,
                    "codeText": code_text,
                    "result": (
                        f"Redirected to a different host: {final_url}\n"
                        "Please make a new WebFetch request with the redirect URL."
                    ),
                    "durationMs": time.time() * 1000 - start_ms,
                    "url": final_url,
                }

        # Truncate and return
        result = text[:MAX_CONTENT_CHARS]
        if len(text) > MAX_CONTENT_CHARS:
            result += f"\n\n[Content truncated — {len(text)} chars total, showing first {MAX_CONTENT_CHARS}]"

        return {
            "bytes": len(raw),
            "code": code,
            "codeText": code_text,
            "result": result,
            "durationMs": time.time() * 1000 - start_ms,
            "url": final_url,
        }

    @staticmethod
    def _is_binary(content_type: str) -> bool:
        ct = content_type.lower().split(";")[0].strip()
        binary_prefixes = (
            "image/",
            "audio/",
            "video/",
            "application/pdf",
            "application/octet-stream",
            "application/zip",
            "application/x-gzip",
        )
        return any(ct.startswith(p) for p in binary_prefixes)

    def map_tool_result(self, content: dict, tool_use_id: str) -> dict:
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": content.get("result", ""),
        }
