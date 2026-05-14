"""Image store for session-scoped pasted content. Ported from utils/imageStore.ts"""

from __future__ import annotations

import asyncio
import base64
import os
from collections import OrderedDict
from pathlib import Path
from typing import Optional

IMAGE_STORE_DIR = "image-cache"
MAX_STORED_IMAGE_PATHS = 200

# In-memory cache: image_id → file path (evicts oldest when capacity exceeded)
_stored_image_paths: OrderedDict = OrderedDict()


def _get_session_id() -> str:
    """Return the current session ID (or a fallback)."""
    try:
        from claude_code.bootstrap.state import get_session_id  # type: ignore[import]

        return get_session_id()
    except Exception:
        return os.environ.get("CLAUDE_SESSION_ID", "default")


def _get_image_store_dir() -> str:
    """Return the image store directory for the current session."""
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir

        base = get_claude_config_home_dir()
    except Exception:
        base = str(Path.home() / ".claude")
    return os.path.join(base, IMAGE_STORE_DIR, _get_session_id())


def _get_image_path(image_id: int, media_type: str) -> str:
    """Return the filesystem path for a stored image."""
    ext = media_type.split("/")[1] if "/" in media_type else "png"
    return os.path.join(_get_image_store_dir(), f"{image_id}.{ext}")


def _evict_oldest_if_at_cap() -> None:
    """Remove the oldest entry if the cache is at capacity."""
    while len(_stored_image_paths) >= MAX_STORED_IMAGE_PATHS:
        _stored_image_paths.popitem(last=False)


def cache_image_path(content: dict) -> Optional[str]:
    """Cache the image path immediately (no file I/O).

    Args:
        content: A PastedContent dict with type='image', id, and mediaType.

    Returns:
        The cached path, or None if content is not an image.
    """
    if content.get("type") != "image":
        return None
    media_type = content.get("mediaType", "image/png")
    image_id = content["id"]
    image_path = _get_image_path(image_id, media_type)
    _evict_oldest_if_at_cap()
    _stored_image_paths[image_id] = image_path
    return image_path


async def store_image(content: dict) -> Optional[str]:
    """Write the image content to disk and cache its path.

    Args:
        content: A PastedContent dict with type='image', id, mediaType, and
            base64-encoded content.

    Returns:
        The path where the image was stored, or None on failure.
    """
    if content.get("type") != "image":
        return None

    media_type = content.get("mediaType", "image/png")
    image_id = content["id"]
    image_path = _get_image_path(image_id, media_type)
    raw_content = content.get("content", "")

    try:
        store_dir = _get_image_store_dir()
        loop = asyncio.get_event_loop()

        def _write() -> None:
            os.makedirs(store_dir, exist_ok=True)
            image_bytes = base64.b64decode(raw_content) if raw_content else b""
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            os.chmod(image_path, 0o600)

        await loop.run_in_executor(None, _write)
        _evict_oldest_if_at_cap()
        _stored_image_paths[image_id] = image_path
        return image_path
    except Exception:
        return None


def get_cached_image_path(image_id: int) -> Optional[str]:
    """Return the cached path for an image, or None if not cached."""
    return _stored_image_paths.get(image_id)


async def clear_image_store() -> None:
    """Delete all stored images for the current session."""
    store_dir = _get_image_store_dir()
    loop = asyncio.get_event_loop()

    def _clear() -> None:
        if not os.path.isdir(store_dir):
            return
        for entry in os.scandir(store_dir):
            try:
                os.unlink(entry.path)
            except Exception:
                pass

    await loop.run_in_executor(None, _clear)
    _stored_image_paths.clear()
