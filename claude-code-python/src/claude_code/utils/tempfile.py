"""
Temp file path generation utilities.
Ported from utils/tempfile.ts
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from typing import Optional


def generate_temp_file_path(
    prefix: str = "claude-prompt",
    extension: str = ".md",
    content_hash: Optional[str] = None,
) -> str:
    """Generate a temporary file path.

    Args:
        prefix: Optional prefix for the temp file name.
        extension: File extension (defaults to ``.md``).
        content_hash: When provided, the identifier is derived from a
            SHA-256 hash of this string (first 16 hex chars). Produces a
            stable path across process boundaries — use when the path ends
            up in content sent to the Anthropic API (e.g., sandbox deny
            lists in tool descriptions) so that a random UUID does not
            invalidate the prompt cache prefix.

    Returns:
        Temp file path (not yet created).
    """
    if content_hash is not None:
        ident = hashlib.sha256(content_hash.encode()).hexdigest()[:16]
    else:
        ident = str(uuid.uuid4())

    filename = f"{prefix}-{ident}{extension}"
    return os.path.join(tempfile.gettempdir(), filename)
