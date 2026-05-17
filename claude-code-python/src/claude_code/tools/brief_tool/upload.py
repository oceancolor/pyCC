"""BriefTool file upload utility. Ported from BriefTool/upload.ts"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

# Maximum upload size — matches the private_api backend limit
MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # 30 MB
UPLOAD_TIMEOUT_MS = 30_000

# Backend dispatches on MIME: image/* → upload_image_wrapped (no ORIGINAL),
# everything else → upload_generic_file (ORIGINAL only, no preview).
# Only whitelist raster formats the transcoder reliably handles.
_MIME_BY_EXT: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _guess_mime_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return _MIME_BY_EXT.get(ext, "application/octet-stream")


def _debug(msg: str) -> None:
    if os.environ.get("CLAUDE_DEBUG"):
        print(f"[brief:upload] {msg}", flush=True)


def _get_bridge_base_url() -> str:
    return (
        os.environ.get("ANTHROPIC_BRIDGE_BASE_URL")
        or os.environ.get("ANTHROPIC_BASE_URL")
        or "https://api.anthropic.com"
    )


class BriefUploadContext:
    """Context for brief attachment uploads."""

    def __init__(self, repl_bridge_enabled: bool, signal: Optional[object] = None) -> None:
        self.repl_bridge_enabled = repl_bridge_enabled
        self.signal = signal


async def upload_brief_attachment(
    full_path: str,
    size: int,
    ctx: BriefUploadContext,
) -> Optional[str]:
    """Upload a single attachment. Returns file_uuid on success, None otherwise.

    Best-effort: any failure (no token, bridge off, network error, 4xx) logs
    debug and returns None. The attachment still carries {path, size, isImage},
    so local-terminal and same-machine-desktop render unaffected.
    """
    if not ctx.repl_bridge_enabled:
        return None

    if size > MAX_UPLOAD_BYTES:
        _debug(f"skip {full_path}: {size} bytes exceeds {MAX_UPLOAD_BYTES} limit")
        return None

    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_ACCESS_TOKEN")
    if not token:
        _debug("skip: no oauth token")
        return None

    try:
        content = Path(full_path).read_bytes()
    except OSError as e:
        _debug(f"read failed for {full_path}: {e}")
        return None

    try:
        import aiohttp  # type: ignore[import]
    except ImportError:
        _debug("skip: aiohttp not available")
        return None

    base_url = _get_bridge_base_url()
    url = f"{base_url}/api/oauth/file_upload"
    filename = Path(full_path).name
    mime_type = _guess_mime_type(filename)
    boundary = f"----FormBoundary{uuid.uuid4().hex}"

    # Manual multipart — matches the TypeScript implementation
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    timeout_s = UPLOAD_TIMEOUT_MS / 1000

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as resp:
                if resp.status != 201:
                    text = await resp.text()
                    _debug(f"upload failed for {full_path}: status={resp.status} body={text[:200]}")
                    return None
                data = await resp.json()
                file_uuid = data.get("file_uuid")
                if not file_uuid:
                    _debug(f"unexpected response shape for {full_path}: {data}")
                    return None
                _debug(f"uploaded {full_path} → {file_uuid} ({size} bytes)")
                return str(file_uuid)
    except Exception as e:
        _debug(f"upload threw for {full_path}: {e}")
        return None


async def upload_attachment(file_path: str) -> Optional[str]:
    """Convenience wrapper for simple uploads (bridge not required).

    Returns None when the bridge environment is unavailable.
    Use upload_brief_attachment() for full context control.
    """
    bridge_enabled = bool(
        os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_ACCESS_TOKEN")
    )
    if not bridge_enabled:
        return None

    try:
        size = Path(file_path).stat().st_size
    except OSError:
        return None

    ctx = BriefUploadContext(repl_bridge_enabled=bridge_enabled)
    return await upload_brief_attachment(file_path, size, ctx)
