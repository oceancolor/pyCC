"""BashTool output utilities. Ported from BashTool/utils.ts"""
from __future__ import annotations
import re
from typing import Optional, Tuple

DATA_URI_RE = re.compile(r'^data:([^;]+);base64,(.+)$', re.DOTALL)
MAX_OUTPUT_LENGTH = 200_000


def strip_empty_lines(content: str) -> str:
    """Strip leading/trailing blank lines while preserving interior whitespace."""
    lines = content.split('\n')
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    end = len(lines) - 1
    while end >= 0 and not lines[end].strip():
        end -= 1
    if start > end:
        return ''
    return '\n'.join(lines[start:end + 1])


def is_image_output(content: str) -> bool:
    return bool(re.match(r'^data:image/[a-z0-9.+_-]+;base64,', content, re.IGNORECASE))


def parse_data_uri(s: str) -> Optional[Tuple[str, str]]:
    """Return (media_type, base64_data) or None."""
    m = DATA_URI_RE.match(s.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


def format_output(content: str) -> dict:
    """Return {total_lines, truncated_content, is_image}."""
    is_image = is_image_output(content)
    if is_image:
        return {"total_lines": 1, "truncated_content": content, "is_image": True}
    if len(content) <= MAX_OUTPUT_LENGTH:
        return {"total_lines": content.count('\n') + 1, "truncated_content": content, "is_image": False}
    truncated = content[:MAX_OUTPUT_LENGTH]
    remaining = content[MAX_OUTPUT_LENGTH:].count('\n') + 1
    return {
        "total_lines": content.count('\n') + 1,
        "truncated_content": f"{truncated}\n\n... [{remaining} lines truncated] ...",
        "is_image": False,
    }


def create_content_summary(content_blocks: list) -> str:
    """Summarize MCP result content blocks."""
    images, texts = 0, []
    for b in content_blocks:
        if b.get("type") == "image":
            images += 1
        elif b.get("type") == "text":
            texts.append(b.get("text", "")[:200])
    parts = []
    if images:
        parts.append(f"[{images} image{'s' if images != 1 else ''}]")
    if texts:
        parts.append(f"[{len(texts)} text block{'s' if len(texts) != 1 else ''}]")
    body = '\n\n'.join(texts) if texts else ''
    summary = ', '.join(parts) if parts else 'empty'
    return f"MCP Result: {summary}" + (f"\n\n{body}" if body else "")
