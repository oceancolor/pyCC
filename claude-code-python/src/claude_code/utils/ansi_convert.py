# 原始 TS: utils/ansiToSvg.ts / utils/ansiToPng.ts (stub)
"""ANSI 转 SVG/PNG（stub）"""
from __future__ import annotations
import re
from typing import Optional


def strip_ansi(text: str) -> str:
    """去除 ANSI 转义序列"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def ansi_to_html(text: str) -> str:
    """将 ANSI 转义转为 HTML（简化版）"""
    text = strip_ansi(text)
    return f"<pre>{text}</pre>"


def ansi_to_svg(text: str, width: int = 80) -> str:
    """ANSI 文本转 SVG（stub）
    TODO: 实现完整的 ANSI → SVG 转换
    """
    plain = strip_ansi(text)
    escaped = plain.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width * 8}" height="400">'
        f'<rect width="100%" height="100%" fill="#1e1e1e"/>'
        f'<text x="10" y="20" fill="#fff" font-family="monospace" font-size="14">'
        f'{escaped}'
        f'</text></svg>'
    )


def ansi_to_png(text: str, output_path: Optional[str] = None) -> Optional[bytes]:
    """ANSI 文本转 PNG（stub，需要 pillow）
    TODO: 实现完整的 PNG 渲染
    """
    return None
