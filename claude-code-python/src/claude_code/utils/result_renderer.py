# 原始 TS: utils/resultRenderer.ts / utils/renderToolResult.ts
"""工具结果渲染（格式化为人类可读输出）"""
from __future__ import annotations
import json
from typing import Any, Optional

try:
    from rich.syntax import Syntax
    from rich.console import Console
    _rich = True
except ImportError:
    _rich = False


def render_tool_result(tool_name: str, result: Any, max_lines: int = 50) -> str:
    """将工具结果格式化为显示字符串"""
    if isinstance(result, str):
        text = result
    elif isinstance(result, (dict, list)):
        text = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        text = str(result)

    lines = text.splitlines()
    if len(lines) > max_lines:
        truncated = len(lines) - max_lines
        lines = lines[:max_lines]
        lines.append(f"... ({truncated} more lines)")
    return "\n".join(lines)


def render_bash_output(stdout: str, stderr: str, returncode: int,
                        max_lines: int = 100) -> str:
    parts = []
    if stdout.strip():
        parts.append(stdout.rstrip())
    if stderr.strip():
        parts.append(f"[stderr]\n{stderr.rstrip()}")
    if returncode != 0:
        parts.append(f"[exit code: {returncode}]")
    combined = "\n".join(parts)
    lines = combined.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(lines)-max_lines} more lines)"]
    return "\n".join(lines)


def render_file_content(path: str, content: str, max_lines: int = 200) -> str:
    lines = content.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(lines)-max_lines} more lines)"]
    numbered = [f"{i+1:4d} │ {l}" for i, l in enumerate(lines)]
    return f"[{path}]\n" + "\n".join(numbered)
