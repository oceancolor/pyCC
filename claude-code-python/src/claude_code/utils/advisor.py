# 原始 TS: utils/advisor.ts
"""智能建议生成器（基于对话状态给出操作建议）"""
from __future__ import annotations
from typing import List, Optional


def suggest_next_action(messages: list, last_error: Optional[str] = None) -> Optional[str]:
    """根据对话历史推断下一步建议"""
    if last_error:
        if "permission" in last_error.lower():
            return "尝试以管理员权限运行，或检查文件权限"
        if "not found" in last_error.lower():
            return "确认文件路径是否正确，或使用 Glob 工具搜索"
        if "syntax" in last_error.lower():
            return "检查代码语法，可能需要修复后重新运行"
    return None


def get_tool_suggestions(recent_tools: List[str]) -> List[str]:
    """根据最近使用的工具推荐下一步工具"""
    suggestions = []
    if "Bash" in recent_tools:
        suggestions.append("使用 FileRead 查看命令输出涉及的文件")
    if "FileRead" in recent_tools:
        suggestions.append("使用 FileEdit 修改文件内容")
    if "Glob" in recent_tools:
        suggestions.append("使用 Grep 在找到的文件中搜索具体内容")
    return suggestions[:2]
