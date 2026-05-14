"""Teleport API client. Ported from utils/teleport/api.ts"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

# Retry delays for transient errors (ms → seconds)
TELEPORT_RETRY_DELAYS_S = [2.0, 4.0, 8.0, 16.0]
MAX_TELEPORT_RETRIES = len(TELEPORT_RETRY_DELAYS_S)

CCR_BYOC_BETA = "ccr-byoc-2025-07-29"


def is_transient_network_error(exc: Exception) -> bool:
    """Return True if ``exc`` is a transient network error worth retrying."""
    try:
        import aiohttp  # type: ignore[import]
        if isinstance(exc, aiohttp.ServerConnectionError):
            return True
        if isinstance(exc, aiohttp.ClientResponseError):
            return exc.status >= 500
    except ImportError:
        pass
    # Socket/connection errors
    import errno as errno_mod
    import socket

    if isinstance(exc, (ConnectionError, TimeoutError, socket.timeout)):
        return True
    return False


async def get_with_retry(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Make a GET request with automatic exponential-backoff retry.

    Retries up to ``MAX_TELEPORT_RETRIES`` times on transient network errors.
    Uses the retry delays defined in ``TELEPORT_RETRY_DELAYS_S``.

    Args:
        url: The URL to request.
        headers: Optional HTTP headers.
        params: Optional query parameters.
        timeout: Per-request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        Exception: If all retries are exhausted.
    """
    try:
        import aiohttp  # type: ignore[import]
    except ImportError:
        raise RuntimeError("aiohttp is required for teleport API calls")

    last_exc: Exception = RuntimeError("No attempts made")

    for attempt in range(MAX_TELEPORT_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers or {},
                    params=params or {},
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    resp.raise_for_status()
                    return await resp.json()
        except Exception as exc:
            last_exc = exc
            if not is_transient_network_error(exc):
                raise
            if attempt < MAX_TELEPORT_RETRIES:
                await asyncio.sleep(TELEPORT_RETRY_DELAYS_S[attempt])

    raise last_exc


async def post_with_retry(
    url: str,
    data: Any,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Make a POST request with automatic exponential-backoff retry.

    Args:
        url: The URL to post to.
        data: JSON-serialisable request body.
        headers: Optional HTTP headers.
        timeout: Per-request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        Exception: If all retries are exhausted.
    """
    try:
        import aiohttp  # type: ignore[import]
    except ImportError:
        raise RuntimeError("aiohttp is required for teleport API calls")

    last_exc: Exception = RuntimeError("No attempts made")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)

    for attempt in range(MAX_TELEPORT_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=data,
                    headers=h,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    resp.raise_for_status()
                    return await resp.json()
        except Exception as exc:
            last_exc = exc
            if not is_transient_network_error(exc):
                raise
            if attempt < MAX_TELEPORT_RETRIES:
                await asyncio.sleep(TELEPORT_RETRY_DELAYS_S[attempt])

    raise last_exc
