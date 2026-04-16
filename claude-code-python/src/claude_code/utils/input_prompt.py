# 原始 TS: utils/inputPrompt.ts / utils/multilineInput.ts
"""多行输入处理（REPL 中的多行编辑）"""
from __future__ import annotations
from typing import List, Optional


def is_continuation_line(line: str) -> bool:
    """判断是否为续行（末尾有 \）"""
    return line.endswith("\\")


def join_continuation_lines(lines: List[str]) -> str:
    """合并续行"""
    result = []
    for line in lines:
        if line.endswith("\\"):
            result.append(line[:-1])
        else:
            result.append(line)
            break
    return "\n".join(result)


def is_complete_input(text: str) -> bool:
    """判断输入是否完整（没有未闭合的括号/引号等）"""
    stack = []
    pairs = {"(": ")", "[": "]", "{": "}"}
    in_string = None
    for ch in text:
        if in_string:
            if ch == in_string:
                in_string = None
        elif ch in ('"', "'", "`"):
            in_string = ch
        elif ch in pairs:
            stack.append(pairs[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
    return len(stack) == 0 and in_string is None


def strip_trailing_whitespace(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()
