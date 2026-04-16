# 原始 TS: utils/controlMessageCompat.ts
"""控制消息兼容层（处理旧版/新版消息格式差异）"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def normalize_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """将各种格式的消息归一化为标准格式"""
    role = msg.get("role", "user")
    content = msg.get("content", "")
    # 旧版：content 是字符串
    if isinstance(content, str):
        return {"role": role, "content": content}
    # 新版：content 是 block 数组
    if isinstance(content, list):
        return {"role": role, "content": content}
    return {"role": role, "content": str(content)}


def extract_text_content(msg: Dict[str, Any]) -> str:
    """从消息中提取纯文本"""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content)


def is_tool_use_message(msg: Dict[str, Any]) -> bool:
    content = msg.get("content", [])
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content)


def is_tool_result_message(msg: Dict[str, Any]) -> bool:
    content = msg.get("content", [])
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
