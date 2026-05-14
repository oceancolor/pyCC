"""ANSI terminal text to PNG converter. Ported from utils/ansiToPng.ts"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
from typing import Optional

from .ansi_to_svg import AnsiToSvgOptions, ansi_to_svg


async def ansi_to_png(
    ansi_text: str,
    output_path: Optional[str] = None,
    options: Optional[AnsiToSvgOptions] = None,
    scale: float = 2.0,
) -> Optional[bytes]:
    """Convert ANSI-escaped terminal text to PNG image bytes.

    Renders via SVG → PNG using either:
    1. ``cairosvg`` Python library (preferred, no external process)
    2. ``rsvg-convert`` CLI tool
    3. Chromium headless (fallback)

    Args:
        ansi_text: The ANSI-escaped text to render.
        output_path: If provided, write the PNG to this path. Otherwise return bytes.
        options: SVG rendering options (font size, padding, background, etc.)
        scale: Device-pixel ratio for high-DPI output (default 2x).

    Returns:
        PNG bytes if ``output_path`` is None, or None if a file was written.

    Raises:
        RuntimeError: If no suitable PNG renderer was found.
    """
    svg_content = ansi_to_svg(ansi_text, options)
    png_bytes = await _svg_to_png(svg_content, scale=scale)

    if output_path is not None:
        with open(output_path, "wb") as f:
            f.write(png_bytes)
        return None

    return png_bytes


async def _svg_to_png(svg_content: str, scale: float = 2.0) -> bytes:
    """Convert SVG content to PNG bytes using the best available method."""
    # Method 1: cairosvg
    try:
        import cairosvg  # type: ignore[import]

        return cairosvg.svg2png(  # type: ignore[no-any-return]
            bytestring=svg_content.encode("utf-8"),
            scale=scale,
        )
    except ImportError:
        pass

    # Method 2: rsvg-convert
    try:
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            svg_path = f.name
            f.write(svg_content.encode("utf-8"))
        try:
            result = subprocess.run(
                ["rsvg-convert", "--dpi-x", str(int(96 * scale)), "--dpi-y", str(int(96 * scale)), svg_path],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
        finally:
            os.unlink(svg_path)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Method 3: inkscape
    try:
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            svg_path = f.name
            f.write(svg_content.encode("utf-8"))
        png_path = svg_path.replace(".svg", ".png")
        try:
            result = subprocess.run(
                [
                    "inkscape",
                    svg_path,
                    "--export-type=png",
                    f"--export-dpi={int(96 * scale)}",
                    f"--export-filename={png_path}",
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0 and os.path.exists(png_path):
                with open(png_path, "rb") as f:
                    return f.read()
        finally:
            for p in (svg_path, png_path):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    raise RuntimeError(
        "No SVG→PNG renderer available. Install cairosvg, rsvg-convert, or inkscape."
    )
