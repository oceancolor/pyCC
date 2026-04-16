# 原始 TS: utils/permissions.ts（工具权限系统）
"""工具权限控制"""
from __future__ import annotations
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set


class PermissionLevel(str, Enum):
    NONE = "none"         # 禁止
    ASK = "ask"           # 每次询问
    AUTO = "auto"         # 自动允许（会话内）
    ALWAYS = "always"     # 永久允许


@dataclass
class ToolPermission:
    tool_name: str
    level: PermissionLevel
    patterns: List[str]   # 允许的路径/命令模式


class PermissionManager:
    def __init__(self) -> None:
        self._permissions: Dict[str, PermissionLevel] = {}
        self._session_granted: Set[str] = set()
        self._setup_defaults()

    def _setup_defaults(self) -> None:
        # 文件读取默认允许
        self._permissions["FileRead"] = PermissionLevel.AUTO
        self._permissions["Glob"] = PermissionLevel.AUTO
        self._permissions["Grep"] = PermissionLevel.AUTO
        # 文件写入需询问
        self._permissions["FileWrite"] = PermissionLevel.ASK
        self._permissions["FileEdit"] = PermissionLevel.ASK
        # Bash 需询问
        self._permissions["Bash"] = PermissionLevel.ASK

    def get_level(self, tool_name: str) -> PermissionLevel:
        if tool_name in self._session_granted:
            return PermissionLevel.AUTO
        return self._permissions.get(tool_name, PermissionLevel.ASK)

    def grant_session(self, tool_name: str) -> None:
        self._session_granted.add(tool_name)

    def set_level(self, tool_name: str, level: PermissionLevel) -> None:
        self._permissions[tool_name] = level

    def is_allowed(self, tool_name: str) -> bool:
        level = self.get_level(tool_name)
        return level in (PermissionLevel.AUTO, PermissionLevel.ALWAYS)


_manager = PermissionManager()

def get_permission_manager() -> PermissionManager:
    return _manager
