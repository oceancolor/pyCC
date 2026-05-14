"""Clipboard image paste utilities. Ported from utils/imagePaste.ts"""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

PASTE_THRESHOLD = 800  # chars; above this, text is treated as a "large paste"

# Max dimensions for pasted images (matches API limits)
IMAGE_MAX_WIDTH = 1568
IMAGE_MAX_HEIGHT = 1568

_BASE_TMP_DIR = (
    os.environ.get("CLAUDE_CODE_TMPDIR")
    or (os.environ.get("TEMP", "C:\\Temp") if sys.platform == "win32" else "/tmp")
)
_SCREENSHOT_PATH = os.path.join(_BASE_TMP_DIR, "claude_cli_latest_screenshot.png")


def _cleanup_screenshot() -> None:
    """Delete the temp screenshot file (best-effort)."""
    try:
        os.unlink(_SCREENSHOT_PATH)
    except FileNotFoundError:
        pass


async def _run_cmd(cmd: str, timeout: float = 5.0) -> Tuple[int, bytes, bytes]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return -1, b"", b"timeout"
    return proc.returncode or 0, stdout, stderr


async def check_clipboard_has_image() -> bool:
    """Return True if the system clipboard currently contains an image."""
    platform = sys.platform
    if platform == "darwin":
        rc, _, _ = await _run_cmd("osascript -e 'the clipboard as «class PNGf»'")
        return rc == 0
    if platform.startswith("linux"):
        rc, out, _ = await _run_cmd(
            'xclip -selection clipboard -t TARGETS -o 2>/dev/null | '
            'grep -E "image/(png|jpeg|jpg|gif|webp|bmp)" || '
            'wl-paste -l 2>/dev/null | grep -E "image/(png|jpeg|jpg|gif|webp|bmp)"'
        )
        return rc == 0 and bool(out.strip())
    if platform == "win32":
        rc, out, _ = await _run_cmd(
            'powershell -NoProfile -Command "(Get-Clipboard -Format Image) -ne $null"',
            timeout=10,
        )
        return rc == 0 and out.strip().lower() in (b"true", b"true\r\n")
    return False


async def paste_clipboard_image() -> Optional[bytes]:
    """Extract the current clipboard image as PNG bytes.

    Returns None if no image is on the clipboard or extraction fails.
    """
    platform = sys.platform
    if platform == "darwin":
        cmd = (
            f"osascript "
            f"-e 'set png_data to (the clipboard as «class PNGf»)' "
            f"-e 'set fp to open for access POSIX file \"{_SCREENSHOT_PATH}\" with write permission' "
            f"-e 'write png_data to fp' "
            f"-e 'close access fp'"
        )
        rc, _, _ = await _run_cmd(cmd)
        if rc != 0 or not os.path.exists(_SCREENSHOT_PATH):
            return None
        try:
            with open(_SCREENSHOT_PATH, "rb") as f:
                return f.read()
        finally:
            _cleanup_screenshot()

    if platform.startswith("linux"):
        cmd = (
            f'xclip -selection clipboard -t image/png -o > "{_SCREENSHOT_PATH}" 2>/dev/null || '
            f'wl-paste --type image/png > "{_SCREENSHOT_PATH}" 2>/dev/null'
        )
        rc, _, _ = await _run_cmd(cmd)
        if rc != 0 or not os.path.exists(_SCREENSHOT_PATH):
            return None
        try:
            with open(_SCREENSHOT_PATH, "rb") as f:
                return f.read()
        finally:
            _cleanup_screenshot()

    if platform == "win32":
        cmd = (
            f'powershell -NoProfile -Command '
            f'"$img = Get-Clipboard -Format Image; if ($img) {{ $img.Save(\'{_SCREENSHOT_PATH.replace(chr(92), chr(92)+chr(92))}\', '
            f'[System.Drawing.Imaging.ImageFormat]::Png) }}"'
        )
        rc, _, _ = await _run_cmd(cmd, timeout=10)
        if rc != 0 or not os.path.exists(_SCREENSHOT_PATH):
            return None
        try:
            with open(_SCREENSHOT_PATH, "rb") as f:
                return f.read()
        finally:
            _cleanup_screenshot()

    return None


async def paste_clipboard_image_as_base64() -> Optional[Tuple[str, str]]:
    """Extract the clipboard image and return (media_type, base64_data).

    Returns None if no image is available.
    """
    raw = await paste_clipboard_image()
    if raw is None:
        return None

    # Detect media type from magic bytes
    if raw[:4] == b"\x89PNG":
        media_type = "image/png"
    elif raw[:3] in (b"\xff\xd8\xff",):
        media_type = "image/jpeg"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        media_type = "image/webp"
    else:
        media_type = "image/png"  # assume PNG

    b64 = base64.b64encode(raw).decode("ascii")
    return media_type, b64


async def get_clipboard_file_path() -> Optional[str]:
    """Return the file path from the clipboard text content, or None."""
    platform = sys.platform
    if platform == "darwin":
        rc, out, _ = await _run_cmd("osascript -e 'get POSIX path of (the clipboard as «class furl»)'")
        if rc == 0 and out.strip():
            path = out.decode("utf-8", errors="replace").strip()
            return path if os.path.exists(path) else None
    if platform.startswith("linux"):
        rc, out, _ = await _run_cmd("xclip -selection clipboard -t text/plain -o 2>/dev/null || wl-paste 2>/dev/null")
        if rc == 0 and out.strip():
            path = out.decode("utf-8", errors="replace").strip()
            return path if os.path.exists(path) else None
    if platform == "win32":
        rc, out, _ = await _run_cmd("powershell -NoProfile -Command \"Get-Clipboard\"", timeout=10)
        if rc == 0 and out.strip():
            path = out.decode("utf-8", errors="replace").strip()
            return path if os.path.exists(path) else None
    return None
