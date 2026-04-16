"""
Temporary file path generation. Ported from tempfile.ts
"""
from __future__ import annotations
import hashlib
import tempfile as _tempfile
import os
import uuid
from typing import Optional


def generate_temp_file_path(prefix: str = "claude-prompt",
                             extension: str = ".md",
                             content_hash: Optional[str] = None) -> str:
    """
    Generate a temporary file path.
    
    If content_hash is provided, the path is stable (same hash → same path).
    """
    if content_hash is not None:
        identifier = hashlib.sha256(content_hash.encode()).hexdigest()[:16]
    else:
        identifier = str(uuid.uuid4())
    return os.path.join(_tempfile.gettempdir(), f"{prefix}-{identifier}{extension}")
