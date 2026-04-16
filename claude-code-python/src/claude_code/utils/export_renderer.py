# 原始 TS: utils/exportRenderer.ts
"""对话导出（Markdown / JSON / HTML）"""
from __future__ import annotations
import json
import time
from typing import Any, Dict, List, Optional


def export_to_markdown(messages: List[Dict[str, Any]],
                        title: Optional[str] = None) -> str:
    lines = []
    if title:
        lines.append(f"# {title}\n")
    lines.append(f"*导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n")
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        icon = "👤" if role == "user" else "🤖"
        lines.append(f"\n## {icon} {role.capitalize()}\n")
        if isinstance(content, str):
            lines.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        lines.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        lines.append(f"\n```tool:{block.get('name','')}\n"
                                     f"{json.dumps(block.get('input',{}), indent=2, ensure_ascii=False)}\n```")
    return "\n".join(lines)


def export_to_json(messages: List[Dict[str, Any]]) -> str:
    return json.dumps(messages, indent=2, ensure_ascii=False)


def export_to_html(messages: List[Dict[str, Any]], title: str = "Claude Conversation") -> str:
    md = export_to_markdown(messages, title)
    escaped = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:sans-serif;max-width:800px;margin:auto;padding:20px}}</style>
</head><body><pre>{escaped}</pre></body></html>"""
