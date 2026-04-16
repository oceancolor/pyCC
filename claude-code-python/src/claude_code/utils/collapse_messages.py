# 原始 TS: utils/collapseReadSearch.ts / utils/collapseHookSummaries.ts
# utils/collapseBackgroundBashNotifications.ts / utils/collapseTeammateShutdowns.ts
"""消息折叠工具（将重复/冗长消息合并为摘要）"""
from __future__ import annotations
from typing import Any, Dict, List


def collapse_consecutive_tool_results(messages: List[Dict[str, Any]],
                                       max_results: int = 3) -> List[Dict[str, Any]]:
    """将连续超过 max_results 条的 tool_result 折叠为摘要"""
    result = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        content = msg.get("content", [])
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            # 收集连续的 tool_result 消息
            group = [msg]
            j = i + 1
            while j < len(messages):
                next_content = messages[j].get("content", [])
                if isinstance(next_content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in next_content
                ):
                    group.append(messages[j])
                    j += 1
                else:
                    break
            if len(group) > max_results:
                summary = {
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": f"[{len(group)} 个工具调用结果已折叠]",
                    }],
                    "_collapsed": True,
                    "_original_count": len(group),
                }
                result.append(summary)
            else:
                result.extend(group)
            i = j
        else:
            result.append(msg)
            i += 1
    return result


def collapse_read_search_results(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """专门折叠文件读取和搜索结果（内容通常很长）"""
    # TODO: 针对 FileRead/Glob/Grep 的结果做智能截断
    return collapse_consecutive_tool_results(messages)
