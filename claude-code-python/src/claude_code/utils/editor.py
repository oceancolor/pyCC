# 原始 TS: utils/editor.ts
"""外部编辑器集成（$EDITOR / $VISUAL）"""
from __future__ import annotations
import os
import subprocess
import tempfile
from typing import Optional


def get_editor() -> str:
    return os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"


def open_in_editor(content: str = "", suffix: str = ".txt") -> Optional[str]:
    """在外部编辑器中编辑内容，返回修改后的内容"""
    editor = get_editor()
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        result = subprocess.run([editor, tmp_path])
        if result.returncode == 0:
            return open(tmp_path).read()
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def edit_file(path: str) -> int:
    """直接用编辑器打开文件，返回退出码"""
    return subprocess.run([get_editor(), path]).returncode
