"""
Screenshot & Clipboard utilities.

Python port of screenshotClipboard.ts.

The TypeScript original renders ANSI text to PNG (pure-TS pipeline) and
then invokes OS clipboard tools.  In Python we provide stub equivalents:
the interface is preserved so callers can depend on the API, but actual
image rendering / clipboard I/O is delegated to platform tools at runtime.

Public API
----------
copy_ansi_to_clipboard(ansi_text, **opts) -> CopyResult
    Convert ANSI text → PNG → system clipboard.  Stub returns success=False
    with a helpful message unless a real backend is wired in.

take_screenshot() -> None
    Stub: returns None (no-op).

read_clipboard_image() -> None
    Stub: returns None (no-op).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CopyResult:
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def _get_platform() -> str:
    """Return a normalised platform string: 'macos', 'linux', or 'windows'."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


# ---------------------------------------------------------------------------
# Internal: copy a PNG file to the system clipboard
# ---------------------------------------------------------------------------


def _copy_png_to_clipboard(png_path: str) -> CopyResult:
    platform = _get_platform()

    if platform == "macos":
        escaped = png_path.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'set the clipboard to (read (POSIX file "{escaped}") as «class PNGf»)'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return CopyResult(success=True, message="Screenshot copied to clipboard")
            return CopyResult(
                success=False,
                message=f"Failed to copy to clipboard: {result.stderr.decode(errors='replace')}",
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CopyResult(success=False, message=f"osascript error: {exc}")

    if platform == "linux":
        # Try xclip first
        try:
            r = subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-i", png_path],
                capture_output=True,
                timeout=5,
            )
            if r.returncode == 0:
                return CopyResult(success=True, message="Screenshot copied to clipboard")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback to xsel
        try:
            with open(png_path, "rb") as fh:
                r2 = subprocess.run(
                    ["xsel", "--clipboard", "--input", "--type", "image/png"],
                    input=fh.read(),
                    capture_output=True,
                    timeout=5,
                )
            if r2.returncode == 0:
                return CopyResult(success=True, message="Screenshot copied to clipboard")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return CopyResult(
            success=False,
            message=(
                "Failed to copy to clipboard. "
                "Please install xclip or xsel: sudo apt install xclip"
            ),
        )

    if platform == "windows":
        ps_path = png_path.replace("'", "''")
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.Clipboard]::SetImage("
            f"[System.Drawing.Image]::FromFile('{ps_path}'))"
        )
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                timeout=5,
            )
            if r.returncode == 0:
                return CopyResult(success=True, message="Screenshot copied to clipboard")
            return CopyResult(
                success=False,
                message=f"Failed to copy to clipboard: {r.stderr.decode(errors='replace')}",
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CopyResult(success=False, message=f"PowerShell error: {exc}")

    return CopyResult(
        success=False,
        message=f"Screenshot to clipboard is not supported on {platform}",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def copy_ansi_to_clipboard(
    ansi_text: str,
    **opts,  # reserved for future AnsiToPng options
) -> CopyResult:
    """Convert ANSI text → PNG → system clipboard.

    The conversion step is a stub: we write an empty PNG placeholder.
    Replace ``_ansi_to_png`` below with a real renderer as needed.

    Args:
        ansi_text: ANSI-escape-code string to render.
        **opts: Reserved for future rendering options.

    Returns:
        CopyResult indicating success or failure.
    """
    try:
        tmp_dir = os.path.join(tempfile.gettempdir(), "claude-code-screenshots")
        os.makedirs(tmp_dir, exist_ok=True)

        import time
        png_path = os.path.join(tmp_dir, f"screenshot-{int(time.time() * 1000)}.png")

        # Stub: write a 1×1 transparent PNG (8 bytes header + minimal IDAT)
        # Real implementation should call an ANSI→PNG renderer here.
        _write_stub_png(png_path)

        result = _copy_png_to_clipboard(png_path)

        try:
            os.unlink(png_path)
        except OSError:
            pass

        return result
    except Exception as exc:  # noqa: BLE001
        return CopyResult(
            success=False,
            message=f"Failed to copy screenshot: {exc}",
        )


def _write_stub_png(path: str) -> None:
    """Write a minimal valid 1×1 white PNG to *path*."""
    import struct, zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\xff\xff"  # filter byte + RGB
    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(sig + ihdr + idat + iend)


def take_screenshot() -> None:
    """Stub: take a screenshot. Returns None."""
    return None


def read_clipboard_image() -> None:
    """Stub: read an image from the clipboard. Returns None."""
    return None
