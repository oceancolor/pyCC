"""ANSI terminal text to SVG converter. Ported from utils/ansiToSvg.ts"""

from __future__ import annotations

import re
import xml.sax.saxutils as saxutils
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Default terminal colour palette (xterm-256 index 0–15)
_PALETTE: Dict[int, Tuple[int, int, int]] = {
    0: (12, 12, 12), 1: (197, 15, 31), 2: (19, 161, 14), 3: (193, 156, 0),
    4: (0, 55, 218), 5: (136, 23, 152), 6: (58, 150, 221), 7: (204, 204, 204),
    8: (118, 118, 118), 9: (231, 72, 86), 10: (22, 198, 12), 11: (249, 241, 165),
    12: (59, 120, 255), 13: (180, 0, 158), 14: (97, 214, 214), 15: (242, 242, 242),
}

_DEFAULT_FG = (204, 204, 204)
_DEFAULT_BG = (12, 12, 12)
_ANSI_RE = re.compile(r'\x1b\[([0-9;]*)m')


@dataclass
class _Span:
    text: str
    color: Tuple[int, int, int] = _DEFAULT_FG
    bold: bool = False


def _ansi_256_to_rgb(index: int) -> Tuple[int, int, int]:
    if index < 16:
        return _PALETTE.get(index, _DEFAULT_FG)
    if index < 232:
        i = index - 16
        r, g, b = i // 36, (i % 36) // 6, i % 6
        return (0 if r == 0 else 55 + r * 40, 0 if g == 0 else 55 + g * 40, 0 if b == 0 else 55 + b * 40)
    gray = (index - 232) * 10 + 8
    return (gray, gray, gray)


def _parse_ansi(text: str) -> List[List[_Span]]:
    """Parse ANSI-escaped text into lines of styled spans."""
    lines: List[List[_Span]] = []
    current_line: List[_Span] = []
    current_color = _DEFAULT_FG
    bold = False
    pos = 0

    for m in _ANSI_RE.finditer(text):
        if m.start() > pos:
            seg = text[pos:m.start()]
            for i, part in enumerate(seg.split('\n')):
                if i > 0:
                    lines.append(current_line)
                    current_line = []
                if part:
                    current_line.append(_Span(part, current_color, bold))
        pos = m.end()
        codes = [int(c) for c in m.group(1).split(';') if c] if m.group(1) else [0]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                current_color, bold = _DEFAULT_FG, False
            elif c == 1:
                bold = True
            elif 30 <= c <= 37:
                current_color = _PALETTE.get(c - 30, _DEFAULT_FG)
            elif 90 <= c <= 97:
                current_color = _PALETTE.get(c - 90 + 8, _DEFAULT_FG)
            elif c == 38 and i + 2 < len(codes) and codes[i + 1] == 5:
                current_color = _ansi_256_to_rgb(codes[i + 2])
                i += 2
            elif c == 38 and i + 4 < len(codes) and codes[i + 1] == 2:
                current_color = (codes[i + 2], codes[i + 3], codes[i + 4])
                i += 4
            i += 1

    # Remaining text
    if pos < len(text):
        for i, part in enumerate(text[pos:].split('\n')):
            if i > 0:
                lines.append(current_line)
                current_line = []
            if part:
                current_line.append(_Span(part, current_color, bold))

    lines.append(current_line)
    return lines


@dataclass
class AnsiToSvgOptions:
    font_family: str = "Menlo, Monaco, monospace"
    font_size: int = 14
    line_height: int = 22
    padding_x: int = 24
    padding_y: int = 24
    background_color: Optional[str] = None
    border_radius: int = 8


def ansi_to_svg(ansi_text: str, options: Optional[AnsiToSvgOptions] = None) -> str:
    """Convert ANSI-escaped terminal text to an SVG string."""
    opts = options or AnsiToSvgOptions()
    bg = opts.background_color or f"rgb{_DEFAULT_BG}"
    lines = _parse_ansi(ansi_text)
    while lines and all(not s.text.strip() for s in lines[-1]):
        lines.pop()

    char_w = opts.font_size * 0.6
    max_len = max((sum(len(s.text) for s in line) for line in lines), default=40)
    width = int(max_len * char_w + opts.padding_x * 2)
    height = len(lines) * opts.line_height + opts.padding_y * 2
    r = opts.border_radius

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'  <rect width="100%" height="100%" fill="{bg}" rx="{r}" ry="{r}"/>\n'
        f'  <style>\n    text {{ font-family: {opts.font_family}; font-size: {opts.font_size}px; white-space: pre; }}\n'
        f'    .b {{ font-weight: bold; }}\n  </style>\n'
    )
    for li, spans in enumerate(lines):
        y = opts.padding_y + (li + 1) * opts.line_height - (opts.line_height - opts.font_size) // 2
        svg += f'  <text x="{opts.padding_x}" y="{y}" xml:space="preserve">'
        for span in spans:
            if not span.text:
                continue
            r_val, g_val, b_val = span.color
            cls = ' class="b"' if span.bold else ''
            escaped = saxutils.escape(span.text)
            svg += f'<tspan fill="rgb({r_val},{g_val},{b_val})"{cls}>{escaped}</tspan>'
        svg += '</text>\n'
    svg += '</svg>'
    return svg
