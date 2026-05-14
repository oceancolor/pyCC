"""BriefTool file upload utility stub. Ported from BriefTool/upload.ts"""
from __future__ import annotations
from typing import Optional

# Maximum upload size — matches the private_api backend limit
MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # 30 MB
UPLOAD_TIMEOUT_MS = 30_000


async def upload_attachment(file_path: str) -> Optional[str]:
    """Upload an attachment file and return a file UUID.

    Best-effort: returns None on any failure.
    This stub always returns None (bridge upload not available in this environment).
    """
    return None
