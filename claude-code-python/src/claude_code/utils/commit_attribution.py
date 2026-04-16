"""
commit_attribution.py
Git commit 归因工具：给 commit message 附加 Claude Code 标记，并解析归因信息。
移植自 commitAttribution.ts + attribution.ts 的核心逻辑。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional

PRODUCT_URL = "https://claude.ai/code"
CO_AUTHOR_EMAIL = "noreply@anthropic.com"
GENERATED_MARKER = "🤖 Generated with"
CO_AUTHORED_PREFIX = "Co-Authored-By:"

# 支持的 claude model 系列，用于 sanitize
_MODEL_PATTERNS = [
    ("opus-4-6", "claude-opus-4-6"),
    ("opus-4-5", "claude-opus-4-5"),
    ("opus-4-1", "claude-opus-4-1"),
    ("opus-4", "claude-opus-4"),
    ("sonnet-4-6", "claude-sonnet-4-6"),
    ("sonnet-4-5", "claude-sonnet-4-5"),
    ("sonnet-4", "claude-sonnet-4"),
    ("sonnet-3-7", "claude-sonnet-3-7"),
    ("haiku-4-5", "claude-haiku-4-5"),
    ("haiku-3-5", "claude-haiku-3-5"),
]


@dataclass
class AttributionInfo:
    """从 commit message 解析出的归因信息"""
    model: Optional[str] = None
    session_id: Optional[str] = None
    co_authored_by: Optional[str] = None
    has_generated_marker: bool = False
    claude_percent: Optional[int] = None
    prompt_count: Optional[int] = None


@dataclass
class AttributionSummary:
    """Claude 对一次提交的贡献摘要"""
    claude_percent: int = 0
    claude_chars: int = 0
    human_chars: int = 0
    surfaces: list[str] = field(default_factory=list)


def sanitize_model_name(short_name: str) -> str:
    """将内部 model 名转换为公开名称，防止 codename 泄露。"""
    for pattern, public_name in _MODEL_PATTERNS:
        if pattern in short_name:
            return public_name
    return "claude"


def build_co_authored_line(model_name: str) -> str:
    """构建 Co-Authored-By git trailer 行。"""
    return f"{CO_AUTHORED_PREFIX} {model_name} <{CO_AUTHOR_EMAIL}>"


def build_generated_marker(url: str = PRODUCT_URL) -> str:
    """构建 PR body 归因标记行。"""
    return f"{GENERATED_MARKER} [Claude Code]({url})"


def add_attribution(
    message: str,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
    include_co_authored: bool = True,
    sanitize: bool = True,
) -> str:
    """
    给 commit message 附加 Claude Code 归因信息。

    Args:
        message: 原始 commit message
        model: 模型名（如 claude-opus-4-5），会附加到 Co-Authored-By
        session_id: 会话 ID（可选）
        include_co_authored: 是否添加 Co-Authored-By trailer
        sanitize: 是否对外部 repo 做 model 名脱敏

    Returns:
        附加归因后的 commit message
    """
    if not message:
        return message

    # 确保正文与 trailer 之间有空行（git trailer 规范）
    body = message.rstrip("\n")
    trailers: list[str] = []

    if include_co_authored:
        display_model = model or "Claude"
        if sanitize and model:
            display_model = sanitize_model_name(model)
        trailers.append(build_co_authored_line(display_model))

    if session_id:
        trailers.append(f"Claude-Session-Id: {session_id}")

    if not trailers:
        return message

    return body + "\n\n" + "\n".join(trailers) + "\n"


def parse_attribution(message: str) -> AttributionInfo:
    """
    从 commit message 中解析 Claude Code 归因信息。

    Args:
        message: commit message 文本

    Returns:
        AttributionInfo 数据类，包含解析到的字段
    """
    info = AttributionInfo()

    if not message:
        return info

    lines = message.splitlines()

    for line in lines:
        stripped = line.strip()

        # 检测 PR body 标记
        if GENERATED_MARKER in stripped:
            info.has_generated_marker = True
            # 尝试从 "N%-shotted by model-name" 格式提取信息
            pct_match = re.search(r"(\d+)%\s+(\d+)-shotted\s+by\s+([\w\-\.]+)", stripped)
            if pct_match:
                info.claude_percent = int(pct_match.group(1))
                info.prompt_count = int(pct_match.group(2))
                info.model = pct_match.group(3)

        # 解析 Co-Authored-By trailer
        if stripped.lower().startswith("co-authored-by:"):
            rest = stripped[len("co-authored-by:"):].strip()
            info.co_authored_by = rest
            # 提取 model 名（邮箱前的名称部分）
            name_match = re.match(r"^([\w\-\. ]+?)\s*<", rest)
            if name_match and info.model is None:
                info.model = name_match.group(1).strip()

        # 解析 Claude-Session-Id trailer
        if stripped.lower().startswith("claude-session-id:"):
            info.session_id = stripped[len("claude-session-id:"):].strip()

    return info


def compute_content_hash(content: str) -> str:
    """计算内容的 SHA-256 哈希（用于文件变化检测）。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_enhanced_pr_attribution(
    model: str,
    claude_percent: int = 0,
    prompt_count: int = 0,
    memory_access_count: int = 0,
    sanitize: bool = True,
    url: str = PRODUCT_URL,
) -> str:
    """
    构建增强版 PR 归因文本，包含贡献百分比和 N-shotted 信息。

    格式: "🤖 Generated with Claude Code (93% 3-shotted by claude-opus-4-5)"
    """
    display_model = sanitize_model_name(model) if sanitize else model

    if claude_percent == 0 and prompt_count == 0 and memory_access_count == 0:
        return build_generated_marker(url)

    mem_suffix = ""
    if memory_access_count > 0:
        noun = "memory" if memory_access_count == 1 else "memories"
        mem_suffix = f", {memory_access_count} {noun} recalled"

    summary = (
        f"{GENERATED_MARKER} [Claude Code]({url}) "
        f"({claude_percent}% {prompt_count}-shotted by {display_model}{mem_suffix})"
    )
    return summary


def has_attribution(message: str) -> bool:
    """检查 commit message 是否已包含 Claude Code 归因。"""
    if not message:
        return False
    lower = message.lower()
    return (
        GENERATED_MARKER.lower() in lower
        or "co-authored-by:" in lower
        or "claude-session-id:" in lower
    )
