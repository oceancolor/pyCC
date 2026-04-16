# 原始 TS: utils/embeddedTools.ts
"""内嵌工具定义（不通过外部调用的内置工具）"""
from __future__ import annotations
from typing import Any, Dict, List


EMBEDDED_TOOL_NAMES = {
    "exit_plan_mode",
    "request_permission",
    "record_thinking",
}


def is_embedded_tool(name: str) -> bool:
    return name in EMBEDDED_TOOL_NAMES


def exit_plan_mode_tool() -> Dict[str, Any]:
    return {
        "name": "exit_plan_mode",
        "description": "Exit plan mode and proceed with execution",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan": {"type": "string", "description": "Summary of the plan"},
            },
            "required": ["plan"],
        },
    }


def request_permission_tool() -> Dict[str, Any]:
    return {
        "name": "request_permission",
        "description": "Request user permission for a sensitive action",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["action", "reason"],
        },
    }


def get_embedded_tools() -> List[Dict[str, Any]]:
    return [exit_plan_mode_tool(), request_permission_tool()]
