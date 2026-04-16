"""
proxy — HTTP/HTTPS proxy configuration helpers.

Mirrors the core logic of proxy.ts:

  get_proxy_url()          → active proxy URL from environment
  get_no_proxy()           → NO_PROXY value from environment
  should_bypass_proxy()    → whether a URL should skip the proxy
  get_proxy_settings()     → combined ProxySettings dataclass
  create_proxied_session() → aiohttp ClientSession (or httpx.AsyncClient)
                             pre-configured with proxy + NO_PROXY support
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

EnvLike = dict[str, Optional[str]]


def get_proxy_url(env: Optional[EnvLike] = None) -> Optional[str]:
    """
    Return the active proxy URL, preferring lowercase over uppercase.
    Priority: https_proxy > HTTPS_PROXY > http_proxy > HTTP_PROXY
    """
    e: EnvLike = env if env is not None else dict(os.environ)
    return (
        e.get("https_proxy")
        or e.get("HTTPS_PROXY")
        or e.get("http_proxy")
        or e.get("HTTP_PROXY")
    )


def get_no_proxy(env: Optional[EnvLike] = None) -> Optional[str]:
    """Return NO_PROXY value, preferring lowercase."""
    e: EnvLike = env if env is not None else dict(os.environ)
    return e.get("no_proxy") or e.get("NO_PROXY")


def should_bypass_proxy(
    url: str,
    no_proxy: Optional[str] = None,
) -> bool:
    """
    Return True if *url* matches any NO_PROXY entry.

    Supports:
    - exact hostname  ("localhost")
    - domain suffix   (".example.com")
    - wildcard        ("*")
    - host:port       ("example.com:8080")
    - IP addresses    ("127.0.0.1")
    """
    if no_proxy is None:
        no_proxy = get_no_proxy()
    if not no_proxy:
        return False
    if no_proxy == "*":
        return True

    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        port = str(parsed.port) if parsed.port else (
            "443" if parsed.scheme == "https" else "80"
        )
        host_with_port = f"{hostname}:{port}"

        entries = [e.strip().lower() for e in no_proxy.replace(",", " ").split() if e.strip()]
        for pattern in entries:
            if ":" in pattern:
                if host_with_port == pattern:
                    return True
            elif pattern.startswith("."):
                suffix = pattern  # e.g. ".example.com"
                if hostname == pattern[1:] or hostname.endswith(suffix):
                    return True
            else:
                if hostname == pattern:
                    return True
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# ProxySettings dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProxySettings:
    """Resolved proxy configuration."""

    proxy_url: Optional[str]
    no_proxy: Optional[str]
    http_proxy: Optional[str]
    https_proxy: Optional[str]

    def is_configured(self) -> bool:
        return bool(self.proxy_url)

    def should_bypass(self, url: str) -> bool:
        return should_bypass_proxy(url, self.no_proxy)


def get_proxy_settings(env: Optional[EnvLike] = None) -> ProxySettings:
    """Build a ProxySettings from the current environment (or *env* override)."""
    e: EnvLike = env if env is not None else dict(os.environ)
    return ProxySettings(
        proxy_url=get_proxy_url(e),
        no_proxy=get_no_proxy(e),
        http_proxy=e.get("http_proxy") or e.get("HTTP_PROXY"),
        https_proxy=e.get("https_proxy") or e.get("HTTPS_PROXY"),
    )


# ---------------------------------------------------------------------------
# Session factories
# ---------------------------------------------------------------------------

def create_proxied_session(
    proxy_url: Optional[str] = None,
    no_proxy: Optional[str] = None,
    *,
    use_httpx: bool = False,
) -> object:
    """
    Create an async HTTP session pre-configured with the given proxy.

    By default tries to build an **aiohttp.ClientSession**.
    Pass ``use_httpx=True`` to get an **httpx.AsyncClient** instead.

    Both clients are returned unconfigured beyond the proxy — the caller
    is responsible for ``async with`` / ``await session.close()``.

    If neither library is installed an ImportError is raised with a helpful
    message.
    """
    if proxy_url is None:
        proxy_url = get_proxy_url()
    if no_proxy is None:
        no_proxy = get_no_proxy()

    if use_httpx:
        return _make_httpx_client(proxy_url, no_proxy)
    try:
        return _make_aiohttp_session(proxy_url, no_proxy)
    except ImportError:
        return _make_httpx_client(proxy_url, no_proxy)


def _make_aiohttp_session(
    proxy_url: Optional[str],
    no_proxy: Optional[str],
) -> object:
    try:
        import aiohttp  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "aiohttp is required for create_proxied_session(); "
            "install it with: pip install aiohttp"
        ) from exc

    connector = aiohttp.TCPConnector()
    # aiohttp does not natively support NO_PROXY; we expose the raw proxy URL
    # and let callers check should_bypass_proxy() for each request if needed.
    return aiohttp.ClientSession(
        connector=connector,
        **({"proxy": proxy_url} if proxy_url else {}),
    )


def _make_httpx_client(
    proxy_url: Optional[str],
    no_proxy: Optional[str],
) -> object:
    try:
        import httpx  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "httpx is required for create_proxied_session(use_httpx=True); "
            "install it with: pip install httpx"
        ) from exc

    proxies: dict[str, str] = {}
    if proxy_url:
        proxies = {"http://": proxy_url, "https://": proxy_url}

    # httpx supports no_proxy natively via the mounts API in v0.24+
    if no_proxy:
        for host in no_proxy.replace(",", " ").split():
            host = host.strip()
            if host:
                proxies[f"https://{host}"] = ""
                proxies[f"http://{host}"] = ""

    return httpx.AsyncClient(proxies=proxies if proxies else None)


# ---------------------------------------------------------------------------
# Convenience: apply proxy to a single fetch call
# ---------------------------------------------------------------------------

async def proxied_get(url: str, **kwargs: object) -> bytes:
    """
    Simple helper: GET *url* via the configured proxy (skips if NO_PROXY).

    Uses httpx.AsyncClient. Returns raw bytes.
    """
    import httpx  # type: ignore

    settings = get_proxy_settings()
    proxy: Optional[str] = None
    if settings.proxy_url and not settings.should_bypass(url):
        proxy = settings.proxy_url

    async with httpx.AsyncClient(proxy=proxy) as client:
        resp = await client.get(url, **kwargs)  # type: ignore[arg-type]
        resp.raise_for_status()
        return resp.content
