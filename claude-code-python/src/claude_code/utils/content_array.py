# 原始 TS: utils/contentArray.ts
"""Anthropic content block 数组工具"""
from typing import Any, Dict, List, Optional, Union


ContentBlock = Dict[str, Any]
ContentArray = List[ContentBlock]


def text_block(text: str) -> ContentBlock:
    return {"type": "text", "text": text}


def tool_use_block(id: str, name: str, input: Dict[str, Any]) -> ContentBlock:
    return {"type": "tool_use", "id": id, "name": name, "input": input}


def tool_result_block(tool_use_id: str, content: Union[str, ContentArray]) -> ContentBlock:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}


def image_block(source: Dict[str, Any]) -> ContentBlock:
    return {"type": "image", "source": source}


def extract_text(content: Union[str, ContentArray]) -> str:
    """从 content（字符串或 block 数组）提取纯文本"""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def extract_tool_uses(content: Union[str, ContentArray]) -> List[ContentBlock]:
    if isinstance(content, str):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]


def normalize_content(content: Any) -> ContentArray:
    """统一转为 ContentArray 格式"""
    if isinstance(content, str):
        return [text_block(content)]
    if isinstance(content, list):
        return content
    return [text_block(str(content))]
