# 原始 TS: services/vcr.ts
"""VCR (Video Cassette Recorder) service for API call replay in tests.

Records API responses to disk and replays them in test environments,
allowing deterministic tests without live API calls.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _should_use_vcr() -> bool:
    if os.environ.get("NODE_ENV") == "test":
        return True
    if os.environ.get("USER_TYPE") == "ant" and os.environ.get("FORCE_VCR") in ("1", "true"):
        return True
    return False


def _get_vcr_dir() -> Path:
    base = os.environ.get("VCR_DIR") or os.path.expanduser("~/.claude/vcr")
    return Path(base)


def _cassette_path(key: str) -> Path:
    safe = hashlib.sha256(key.encode()).hexdigest()
    return _get_vcr_dir() / f"{safe}.json"


def record_response(key: str, response: Any) -> None:
    """Save an API response under *key* for later playback."""
    if not _should_use_vcr():
        return
    path = _cassette_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(response, indent=2))
    logger.debug("VCR recorded: %s → %s", key[:40], path.name)


def playback_response(key: str) -> Any | None:
    """Return a previously recorded response, or None if not found."""
    if not _should_use_vcr():
        return None
    path = _cassette_path(key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


async def with_token_count_vcr(
    key: str,
    fn: Callable[[], Any],
) -> Any:
    """Return cached token-count result or call *fn* and cache the result."""
    cached = playback_response(key)
    if cached is not None:
        logger.debug("VCR hit: %s", key[:40])
        return cached
    result = await fn() if asyncio.iscoroutinefunction(fn) else fn()
    record_response(key, result)
    return result


import asyncio  # noqa: E402
