# 原始 TS: utils/parseToolResult.ts
"""解析工具调用结果"""
from __future__ import annotations
import json
from typing import Any, Dict, Optional, Tuple, Union


def parse_tool_result(result: Any) -> Tuple[str, bool]:
    """
    将工具结果解析为 (text, is_error) 元组。
    """
    if isinstance(result, str):
        return result, False
    if isinstance(result, dict):
        if "error" in result:
            return str(result["error"]), True
        if "output" in result:
            return str(result["output"]), False
        if "content" in result:
            content = result["content"]
            if isinstance(content, str):
                return content, False
            if isinstance(content, list):
                texts = [b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text"]
                return "\n".join(texts), False
    if isinstance(result, (list, dict)):
        return json.dumps(result, ensure_ascii=False, indent=2), False
    return str(result), False


def format_tool_result_for_api(
    tool_use_id: str,
    result: Any,
    is_error: bool = False,
) -> Dict[str, Any]:
    """构建 tool_result content block"""
    text, detected_error = parse_tool_result(result)
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": text,
        "is_error": is_error or detected_error,
    }
