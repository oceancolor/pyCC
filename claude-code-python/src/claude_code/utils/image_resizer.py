"""Image resizing utilities. Ported from utils/imageResizer.ts"""

from __future__ import annotations

import base64
import io
from typing import Optional, Tuple


def _try_import_pillow() -> Optional[object]:
    """Attempt to import PIL/Pillow. Returns the Image module or None."""
    try:
        from PIL import Image  # type: ignore[import]

        return Image
    except ImportError:
        return None


def _try_import_cv2() -> Optional[object]:
    """Attempt to import OpenCV. Returns the cv2 module or None."""
    try:
        import cv2  # type: ignore[import]

        return cv2
    except ImportError:
        return None


def resize_image_bytes(
    image_bytes: bytes,
    max_width: int = 1568,
    max_height: int = 1568,
    quality: int = 75,
    output_format: str = "JPEG",
) -> Optional[bytes]:
    """Resize image bytes to fit within the given dimensions while maintaining aspect ratio.

    Tries Pillow first, then falls back to returning None if unavailable.

    Args:
        image_bytes: Raw image bytes (JPEG, PNG, WEBP, GIF, etc.)
        max_width: Maximum output width in pixels.
        max_height: Maximum output height in pixels.
        quality: JPEG/WEBP quality (1–100). Ignored for PNG/lossless formats.
        output_format: PIL format string (e.g. 'JPEG', 'PNG', 'WEBP').

    Returns:
        Resized image bytes, or None if resizing is not possible.
    """
    Image = _try_import_pillow()
    if Image is None:
        return None

    try:
        img = Image.open(io.BytesIO(image_bytes))  # type: ignore[attr-defined]
        orig_w, orig_h = img.size

        if orig_w <= max_width and orig_h <= max_height:
            # No resize needed – re-encode at the specified quality
            buf = io.BytesIO()
            if output_format.upper() == "PNG":
                img.save(buf, format=output_format)
            else:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(buf, format=output_format, quality=quality)
            return buf.getvalue()

        # Calculate new size preserving aspect ratio
        ratio_w = max_width / orig_w
        ratio_h = max_height / orig_h
        ratio = min(ratio_w, ratio_h)
        new_w = max(1, int(orig_w * ratio))
        new_h = max(1, int(orig_h * ratio))

        resized = img.resize(  # type: ignore[attr-defined]
            (new_w, new_h),
            Image.LANCZOS,  # type: ignore[attr-defined]
        )

        buf = io.BytesIO()
        if output_format.upper() == "PNG":
            resized.save(buf, format=output_format)
        else:
            if resized.mode in ("RGBA", "P"):
                resized = resized.convert("RGB")
            resized.save(buf, format=output_format, quality=quality)

        return buf.getvalue()
    except Exception:
        return None


def resize_base64_image(
    base64_data: str,
    max_width: int = 1568,
    max_height: int = 1568,
    quality: int = 75,
    output_format: str = "JPEG",
) -> Optional[str]:
    """Resize a base64-encoded image and return the resized base64 string.

    Returns None if the image cannot be resized.
    """
    try:
        raw = base64.b64decode(base64_data)
    except Exception:
        return None

    resized = resize_image_bytes(
        raw,
        max_width=max_width,
        max_height=max_height,
        quality=quality,
        output_format=output_format,
    )
    if resized is None:
        return None

    return base64.b64encode(resized).decode("ascii")


def get_image_dimensions(image_bytes: bytes) -> Optional[Tuple[int, int]]:
    """Return the (width, height) of an image, or None if unreadable."""
    Image = _try_import_pillow()
    if Image is None:
        return None

    try:
        img = Image.open(io.BytesIO(image_bytes))  # type: ignore[attr-defined]
        return img.size  # type: ignore[return-value]
    except Exception:
        return None
