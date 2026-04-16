# 原始 TS: utils/attribution.ts / utils/commitAttribution.ts
"""Commit 归因：标记 AI 生成的提交"""
from __future__ import annotations

import os
import subprocess
from typing import Dict, Optional

ATTRIBUTION_TRAILER = "Co-authored-by: Claude <claude@anthropic.com>"
CLAUDE_CODE_TRAILER = "Generated-by: claude-code"


def add_attribution_to_message(message: str, include_claude_code: bool = True) -> str:
    """在 commit message 末尾添加 Co-authored-by trailer"""
    trailers = [ATTRIBUTION_TRAILER]
    if include_claude_code:
        trailers.append(CLAUDE_CODE_TRAILER)
    trailer_block = "\n".join(trailers)
    if not message.endswith("\n"):
        message += "\n"
    return f"{message}\n{trailer_block}\n"


def get_git_author() -> Optional[Dict[str, str]]:
    """获取当前 git 配置的 author 信息"""
    try:
        name = subprocess.check_output(
            ["git", "config", "user.name"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        email = subprocess.check_output(
            ["git", "config", "user.email"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        return {"name": name, "email": email}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def should_add_attribution() -> bool:
    """是否应该添加归因（检查环境变量开关）"""
    return os.environ.get("CLAUDE_CODE_NO_ATTRIBUTION", "").lower() not in ("1", "true", "yes")
