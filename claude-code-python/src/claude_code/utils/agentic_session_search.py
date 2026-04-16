"""
在历史会话中进行 agentic 语义搜索。

原始 TS: utils/agenticSessionSearch.ts (307 行)

核心思路：
1. 对候选会话做关键词预筛选（低成本）
2. 将候选会话的元数据+片段内容构建成 prompt
3. 调用轻量 LLM 进行语义排序，返回相关会话列表

Python 版本直接基于 SessionInfo（无需 LogOption 类型适配层）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from claude_code.utils.list_sessions_impl import SessionInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_TRANSCRIPT_CHARS = 2000      # 每个会话最多取多少字符的片段
MAX_MESSAGES_TO_SCAN = 100       # 扫描消息上限
MAX_SESSIONS_TO_SEARCH = 100     # 发给 LLM 的候选会话上限

SESSION_SEARCH_SYSTEM_PROMPT = """\
Your goal is to find relevant sessions based on a user's search query.

You will be given a list of sessions with their metadata and a search query. \
Identify which sessions are most relevant to the query.

Each session may include:
- Title (display name or custom title)
- Tag (user-assigned category, shown as [tag: name])
- Branch (git branch name, shown as [branch: name])
- Summary (AI-generated summary)
- First message (beginning of the conversation)

IMPORTANT: Tags are user-assigned labels. Exact tag matches get highest priority.

For each session, consider (in order of priority):
1. Exact tag matches
2. Partial tag / title matches
3. Branch name matches
4. Summary and content matches
5. Semantic similarity

Be VERY inclusive. Include sessions that mention the concept even in passing.
Return sessions ordered by relevance.

Respond with ONLY the JSON object, no markdown formatting:
{"relevant_indices": [2, 5, 0]}"""


# ---------------------------------------------------------------------------
# Minimal message type for transcript extraction
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """简化消息类型，仅保留搜索所需字段。"""
    type: str                   # "user" | "assistant" | ...
    content: Any = None         # str | list[dict] | None


def extract_message_text(message: Message) -> str:
    """从消息中提取可搜索的文本内容。"""
    if message.type not in ("user", "assistant"):
        return ""
    content = message.content
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text", "")
                if isinstance(text, str) and text:
                    parts.append(text)
        return " ".join(parts)
    return ""


def extract_transcript(messages: Sequence[Message]) -> str:
    """从消息列表中提取截断的对话片段。"""
    if not messages:
        return ""

    if len(messages) <= MAX_MESSAGES_TO_SCAN:
        to_scan = list(messages)
    else:
        half = MAX_MESSAGES_TO_SCAN // 2
        to_scan = list(messages[:half]) + list(messages[-half:])

    text = " ".join(
        t for m in to_scan if (t := extract_message_text(m))
    )
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > MAX_TRANSCRIPT_CHARS:
        return text[:MAX_TRANSCRIPT_CHARS] + "…"
    return text


# ---------------------------------------------------------------------------
# Pre-filter: keyword matching
# ---------------------------------------------------------------------------


def session_contains_query(info: SessionInfo, query_lower: str) -> bool:
    """快速检查会话元数据中是否包含查询关键词。"""
    fields = [
        info.summary,
        info.custom_title,
        info.tag,
        info.git_branch,
        info.first_prompt,
        info.cwd,
    ]
    for f in fields:
        if f and query_lower in f.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# LLM call (side query)
# ---------------------------------------------------------------------------


async def _call_llm_for_ranking(
    session_list_text: str,
    query: str,
) -> List[int]:
    """调用 LLM 对候选会话进行语义排序，返回相关索引列表。

    若 LLM 不可用，回退到返回空列表（调用方应已有关键词预筛选结果）。
    """
    try:
        # 尝试导入内部 LLM 调用模块
        from claude_code.utils.api import simple_query  # type: ignore
    except ImportError:
        logger.debug("api.simple_query not available; skipping LLM ranking")
        return []

    user_message = (
        f"Sessions:\n{session_list_text}\n\nSearch query: \"{query}\"\n\n"
        "Find the sessions that are most relevant to this query."
    )

    try:
        response_text = await simple_query(
            system=SESSION_SEARCH_SYSTEM_PROMPT,
            user=user_message,
        )
    except Exception as exc:
        logger.debug("LLM ranking failed: %s", exc)
        return []

    # 从响应中提取 JSON
    m = re.search(r"\{[\s\S]*\}", response_text)
    if not m:
        logger.debug("No JSON found in LLM ranking response")
        return []

    try:
        result: Dict[str, Any] = json.loads(m.group())
        indices = result.get("relevant_indices", [])
        return [i for i in indices if isinstance(i, int)]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.debug("Failed to parse LLM ranking JSON: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Build prompt text
# ---------------------------------------------------------------------------


def _build_session_list_text(
    infos: List[SessionInfo],
    messages_map: Optional[Dict[str, List[Message]]] = None,
) -> str:
    """将会话元数据列表序列化为 prompt 文本。"""
    lines: List[str] = []
    for idx, info in enumerate(infos):
        parts = [f"{idx}:"]

        # 主标题
        title = info.custom_title or info.summary or info.first_prompt or "(no title)"
        parts.append(title)

        if info.custom_title and info.custom_title != title:
            parts.append(f"[custom title: {info.custom_title}]")
        if info.tag:
            parts.append(f"[tag: {info.tag}]")
        if info.git_branch:
            parts.append(f"[branch: {info.git_branch}]")
        if info.summary and info.summary != title:
            parts.append(f"- Summary: {info.summary}")
        if info.first_prompt and info.first_prompt not in (title, "No prompt"):
            parts.append(f"- First message: {info.first_prompt[:300]}")

        # 可选的对话片段
        if messages_map:
            msgs = messages_map.get(info.session_id, [])
            if msgs:
                transcript = extract_transcript(msgs)
                if transcript:
                    parts.append(f"- Transcript: {transcript}")

        lines.append(" ".join(parts))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def search_sessions(
    query: str,
    sessions: List[SessionInfo],
    *,
    limit: Optional[int] = None,
    messages_map: Optional[Dict[str, List[Message]]] = None,
    use_llm: bool = True,
) -> List[SessionInfo]:
    """在历史会话中搜索与 query 相关的会话。

    Args:
        query: 搜索关键词或语义查询
        sessions: 候选会话列表（通常来自 list_sessions_impl）
        limit: 最多返回的会话数
        messages_map: session_id → 消息列表，用于对话片段搜索（可选）
        use_llm: 是否使用 LLM 进行语义排序（默认 True，不可用时自动回退）

    Returns:
        按相关性排序的会话列表
    """
    if not query.strip() or not sessions:
        return []

    query_lower = query.lower()

    # 关键词预筛选
    matching = [s for s in sessions if session_contains_query(s, query_lower)]

    # 组合：匹配的 + 部分非匹配的（填充到 MAX_SESSIONS_TO_SEARCH）
    if len(matching) >= MAX_SESSIONS_TO_SEARCH:
        to_search = matching[:MAX_SESSIONS_TO_SEARCH]
    else:
        non_matching = [s for s in sessions if not session_contains_query(s, query_lower)]
        remaining = MAX_SESSIONS_TO_SEARCH - len(matching)
        to_search = matching + non_matching[:remaining]

    logger.debug(
        "search_sessions: query=%r, total=%d, matching=%d, to_search=%d",
        query, len(sessions), len(matching), len(to_search),
    )

    if not use_llm:
        # 纯关键词模式：matching 在前，其余按原序
        result = matching[:MAX_SESSIONS_TO_SEARCH]
        return result[:limit] if limit else result

    # LLM 语义排序
    session_text = _build_session_list_text(to_search, messages_map)
    relevant_indices = await _call_llm_for_ranking(session_text, query)

    if relevant_indices:
        # 按 LLM 返回的顺序映射回会话对象
        ordered = [
            to_search[i]
            for i in relevant_indices
            if 0 <= i < len(to_search)
        ]
        logger.debug("search_sessions: LLM returned %d relevant sessions", len(ordered))
    else:
        # LLM 不可用或无结果，回退到关键词匹配结果
        logger.debug("search_sessions: falling back to keyword matches")
        ordered = matching

    return ordered[:limit] if limit else ordered


async def agentic_session_search(
    query: str,
    sessions: List[SessionInfo],
    messages_map: Optional[Dict[str, List[Message]]] = None,
) -> List[SessionInfo]:
    """兼容原始 TS API 的入口函数。

    Args:
        query: 搜索查询
        sessions: 候选会话列表
        messages_map: session_id → 消息列表（可选）

    Returns:
        相关会话列表
    """
    return await search_sessions(
        query=query,
        sessions=sessions,
        messages_map=messages_map,
        use_llm=True,
    )
