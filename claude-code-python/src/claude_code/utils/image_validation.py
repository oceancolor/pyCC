"""Image validation for API message payloads. Ported from utils/imageValidation.ts"""

from __future__ import annotations

import base64
from typing import Any, List, Optional

# API limit for base64-encoded image size (5 MB in chars = 5 * 1024 * 1024)
API_IMAGE_MAX_BASE64_SIZE = 5 * 1024 * 1024


class OversizedImage:
    """Information about a single oversized image."""

    def __init__(self, index: int, size: int) -> None:
        self.index = index
        self.size = size


class ImageSizeError(ValueError):
    """Raised when one or more images exceed the API size limit."""

    def __init__(self, oversized_images: List[OversizedImage], max_size: int) -> None:
        def _fmt(n: int) -> str:
            for unit, threshold in [("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)]:
                if n >= threshold:
                    return f"{n / threshold:.1f} {unit}"
            return f"{n} B"

        if len(oversized_images) == 1:
            img = oversized_images[0]
            message = (
                f"Image base64 size ({_fmt(img.size)}) exceeds API limit ({_fmt(max_size)}). "
                "Please resize the image before sending."
            )
        else:
            detail = ", ".join(f"Image {img.index}: {_fmt(img.size)}" for img in oversized_images)
            message = (
                f"{len(oversized_images)} images exceed the API limit ({_fmt(max_size)}): "
                f"{detail}. Please resize these images before sending."
            )
        super().__init__(message)
        self.name = "ImageSizeError"
        self.oversized_images = oversized_images


def _is_base64_image_block(block: Any) -> bool:
    """Return True if ``block`` is a base64 image block."""
    if not isinstance(block, dict):
        return False
    if block.get("type") != "image":
        return False
    source = block.get("source")
    if not isinstance(source, dict):
        return False
    return source.get("type") == "base64" and isinstance(source.get("data"), str)


def validate_images_for_api(
    messages: List[Any],
    max_size: int = API_IMAGE_MAX_BASE64_SIZE,
) -> None:
    """Validate that all images in messages are within the API size limit.

    Args:
        messages: List of message dicts to validate.
        max_size: Maximum allowed base64-encoded size in characters.

    Raises:
        ImageSizeError: If any image exceeds the limit.
    """
    oversized: List[OversizedImage] = []
    image_index = 0

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("type") != "user":
            continue

        inner = msg.get("message")
        if not isinstance(inner, dict):
            continue

        content = inner.get("content", [])
        if not isinstance(content, list):
            continue

        for block in content:
            if not _is_base64_image_block(block):
                continue

            data: str = block["source"]["data"]  # type: ignore[index]
            size = len(data)
            if size > max_size:
                oversized.append(OversizedImage(index=image_index, size=size))
            image_index += 1

    if oversized:
        raise ImageSizeError(oversized, max_size)


def decode_base64_image(data_url_or_b64: str) -> Optional[bytes]:
    """Decode a base64 image string or data: URL to raw bytes.

    Returns None on failure.
    """
    try:
        if data_url_or_b64.startswith("data:"):
            # data:image/png;base64,<data>
            _, b64 = data_url_or_b64.split(",", 1)
            return base64.b64decode(b64)
        return base64.b64decode(data_url_or_b64)
    except Exception:
        return None
