"""
HTTP utility constants and helpers.

Provides:
- HttpError: exception for non-2xx responses
- fetch_url(): async HTTP wrapper (httpx-based, with aiohttp fallback stub)
- get_user_agent() / get_auth_headers(): shared header helpers
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class HttpError(Exception):
    """Raised for HTTP responses with non-2xx status codes."""

    def __init__(
        self,
        message: str,
        status_code: int,
        response_body: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.headers = headers or {}

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"HttpError(status={self.status_code}, message={self.args[0]!r})"
        )


# ---------------------------------------------------------------------------
# Request / Response types
# ---------------------------------------------------------------------------


@dataclass
class FetchOptions:
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    timeout: float = 30.0
    follow_redirects: bool = True


@dataclass
class FetchResponse:
    status_code: int
    headers: dict[str, str]
    text: str

    def json(self) -> Any:
        import json
        return json.loads(self.text)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


# ---------------------------------------------------------------------------
# User-Agent helpers
# ---------------------------------------------------------------------------

def get_user_agent() -> str:
    """Return the claude-cli user-agent string."""
    version = os.environ.get("CLAUDE_CODE_VERSION", "0.0.0")
    user_type = os.environ.get("USER_TYPE", "unknown")
    entrypoint = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "cli")
    sdk_version = os.environ.get("CLAUDE_AGENT_SDK_VERSION", "")
    sdk_suffix = f", agent-sdk/{sdk_version}" if sdk_version else ""
    return f"claude-cli/{version} ({user_type}, {entrypoint}{sdk_suffix})"


def get_mcp_user_agent() -> str:
    """Return the claude-code MCP user-agent string."""
    version = os.environ.get("CLAUDE_CODE_VERSION", "0.0.0")
    parts: list[str] = []
    if ep := os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        parts.append(ep)
    if sv := os.environ.get("CLAUDE_AGENT_SDK_VERSION"):
        parts.append(f"agent-sdk/{sv}")
    suffix = f" ({', '.join(parts)})" if parts else ""
    return f"claude-code/{version}{suffix}"


# ---------------------------------------------------------------------------
# Core fetch function
# ---------------------------------------------------------------------------

async def fetch_url(
    url: str,
    options: Optional[FetchOptions] = None,
) -> FetchResponse:
    """
    Async HTTP request wrapper. Uses httpx when available, otherwise raises
    ImportError with a helpful message.

    Raises:
        HttpError: for non-2xx status codes.
        ImportError: if no HTTP library is available.
    """
    if options is None:
        options = FetchOptions()

    try:
        import httpx
    except ImportError as exc:
        raise ImportError(
            "httpx is required for fetch_url(). Install it with: pip install httpx"
        ) from exc

    async with httpx.AsyncClient(
        follow_redirects=options.follow_redirects,
        timeout=options.timeout,
    ) as client:
        response = await client.request(
            method=options.method,
            url=url,
            headers=options.headers,
            content=options.body.encode() if options.body else None,
        )

    resp = FetchResponse(
        status_code=response.status_code,
        headers=dict(response.headers),
        text=response.text,
    )

    if not resp.ok:
        raise HttpError(
            f"HTTP {response.status_code} {response.reason_phrase}",
            status_code=response.status_code,
            response_body=resp.text,
            headers=resp.headers,
        )

    return resp
