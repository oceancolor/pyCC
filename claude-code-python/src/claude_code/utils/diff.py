# 原始 TS: utils/diff.ts
"""文件差异工具（unified diff）"""
from __future__ import annotations
import difflib
from typing import List


def unified_diff(old: str, new: str, filename: str = "file",
                 context_lines: int = 3) -> str:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}", tofile=f"b/{filename}",
        n=context_lines,
    )
    return "".join(diff)


def count_changes(diff_text: str) -> dict:
    added = sum(1 for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff_text.splitlines() if l.startswith("-") and not l.startswith("---"))
    return {"added": added, "removed": removed}


def apply_diff_preview(original: str, new_content: str, filename: str = "file") -> str:
    diff = unified_diff(original, new_content, filename)
    if not diff:
        return "(no changes)"
    return diff
