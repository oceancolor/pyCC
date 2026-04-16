"""
tool_search.py
工具搜索工具：根据关键词匹配工具名称和描述，返回相关工具列表。
移植自 ToolSearchTool.ts 的核心搜索逻辑，去掉 MCP/analytics/React 相关内容。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolDefinition:
    """工具定义（轻量级结构，便于搜索）"""
    name: str
    description: str = ""
    search_hint: str = ""  # 额外搜索提示，信号强度高于普通描述
    is_mcp: bool = False   # 是否为 MCP 工具（mcp__server__action 格式）


@dataclass
class SearchResult:
    """搜索结果，包含工具名和相关性分数"""
    name: str
    score: float
    tool: ToolDefinition


def _escape_regex(text: str) -> str:
    """转义正则特殊字符。"""
    return re.escape(text)


def _parse_tool_name(name: str) -> dict:
    """
    将工具名解析为可搜索的组成部分。
    - MCP 工具：mcp__server__action → ['server', 'action', ...]
    - 普通工具：CamelCaseName → ['camel', 'case', 'name']
    """
    if name.startswith("mcp__"):
        without_prefix = name[5:].lower()
        parts = [p for segment in without_prefix.split("__")
                 for p in segment.split("_") if p]
        full = without_prefix.replace("__", " ").replace("_", " ")
        return {"parts": parts, "full": full, "is_mcp": True}

    # CamelCase → snake → words
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    parts = [p for p in re.split(r"[\s_]+", spaced.lower()) if p]
    return {"parts": parts, "full": " ".join(parts), "is_mcp": False}


def _compile_term_patterns(terms: list[str]) -> dict[str, re.Pattern]:
    """预编译每个搜索词的词边界正则，避免重复编译。"""
    patterns: dict[str, re.Pattern] = {}
    for term in terms:
        if term not in patterns:
            try:
                patterns[term] = re.compile(r"\b" + _escape_regex(term) + r"\b")
            except re.error:
                # 回退：普通包含匹配
                patterns[term] = re.compile(_escape_regex(term))
    return patterns


def search_tools(
    query: str,
    tools: list[ToolDefinition],
    max_results: int = 5,
) -> list[ToolDefinition]:
    """
    根据关键词搜索工具列表，返回匹配的工具（按相关性排序）。

    支持：
    - 精确名称匹配（最高优先级）
    - mcp__server 前缀匹配
    - select:<tool_name> 直接选择语法
    - 关键词得分排序（名称部分 > hint > 描述）
    - +term 语法要求某词必须匹配

    Args:
        query: 搜索关键词
        tools: 工具列表
        max_results: 最多返回结果数

    Returns:
        匹配工具列表（已去重，按相关性降序）
    """
    results = rank_tools(query, tools, max_results)
    return [r.tool for r in results]


def rank_tools(
    query: str,
    tools: list[ToolDefinition],
    max_results: int = 10,
) -> list[SearchResult]:
    """
    对工具列表按与查询的相关性评分并排序。

    Args:
        query: 搜索关键词
        tools: 工具列表
        max_results: 最多返回结果数

    Returns:
        SearchResult 列表，按 score 降序，score > 0
    """
    if not query or not tools:
        return []

    query_lower = query.lower().strip()

    # select:<name> 直接选择语法
    if query_lower.startswith("select:"):
        target = query_lower[7:].strip()
        for tool in tools:
            if tool.name.lower() == target:
                return [SearchResult(name=tool.name, score=100.0, tool=tool)]
        return []

    # 精确名称匹配
    exact = next((t for t in tools if t.name.lower() == query_lower), None)
    if exact:
        return [SearchResult(name=exact.name, score=100.0, tool=exact)]

    # mcp__ 前缀匹配
    if query_lower.startswith("mcp__") and len(query_lower) > 5:
        prefix_matches = [
            SearchResult(name=t.name, score=90.0, tool=t)
            for t in tools if t.name.lower().startswith(query_lower)
        ]
        if prefix_matches:
            return prefix_matches[:max_results]

    # 拆分搜索词，处理 +required 语法
    raw_terms = [t for t in query_lower.split() if t]
    required_terms: list[str] = []
    optional_terms: list[str] = []
    for term in raw_terms:
        if term.startswith("+") and len(term) > 1:
            required_terms.append(term[1:])
        else:
            optional_terms.append(term)

    scoring_terms = (required_terms + optional_terms) if required_terms else raw_terms
    term_patterns = _compile_term_patterns(scoring_terms)

    # 过滤：必须包含所有 required_terms
    candidates = tools
    if required_terms:
        filtered = []
        for tool in tools:
            parsed = _parse_tool_name(tool.name)
            desc_low = tool.description.lower()
            hint_low = tool.search_hint.lower()
            if all(
                parsed["parts"].__contains__(rt)
                or any(rt in part for part in parsed["parts"])
                or term_patterns[rt].search(desc_low)
                or (hint_low and term_patterns[rt].search(hint_low))
                for rt in required_terms
            ):
                filtered.append(tool)
        candidates = filtered

    # 评分
    scored: list[SearchResult] = []
    for tool in candidates:
        parsed = _parse_tool_name(tool.name)
        desc_low = tool.description.lower()
        hint_low = tool.search_hint.lower()
        score = 0.0

        for term in scoring_terms:
            pattern = term_patterns[term]

            # 工具名部分精确匹配（MCP server 名权重更高）
            if term in parsed["parts"]:
                score += 12.0 if parsed["is_mcp"] else 10.0
            elif any(term in part for part in parsed["parts"]):
                score += 6.0 if parsed["is_mcp"] else 5.0
            elif term in parsed["full"] and score == 0:
                score += 3.0

            # searchHint（精选能力描述，信号质量高）
            if hint_low and pattern.search(hint_low):
                score += 4.0

            # 描述词边界匹配
            if desc_low and pattern.search(desc_low):
                score += 2.0

        if score > 0:
            scored.append(SearchResult(name=tool.name, score=score, tool=tool))

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:max_results]


def filter_tools_by_name(
    pattern: str,
    tools: list[ToolDefinition],
    case_sensitive: bool = False,
) -> list[ToolDefinition]:
    """
    按名称模式过滤工具（支持 glob 风格的 * 通配符）。

    Args:
        pattern: 匹配模式，如 "mcp__*" 或 "File*"
        tools: 工具列表
        case_sensitive: 是否区分大小写

    Returns:
        匹配的工具列表
    """
    regex_pattern = re.escape(pattern).replace(r"\*", ".*")
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        compiled = re.compile(f"^{regex_pattern}$", flags)
    except re.error:
        return []
    return [t for t in tools if compiled.match(t.name)]
