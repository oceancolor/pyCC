# 原始 TS: utils/crossProjectResume.ts
"""跨项目 session 恢复检查

检查某个日志是否来自不同的项目目录，并判断它是关联的 worktree 还是
完全不同的项目。对于同一仓库的 worktree，可直接恢复；对不同项目，生成 cd 命令。
"""
from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from uuid import UUID


# LogOption 类型别名（与 session_storage 保持一致）
LogOption = Dict[str, Any]


@dataclass
class CrossProjectResumeNotCross:
    """非跨项目情形"""
    is_cross_project: bool = field(default=False, init=False)


@dataclass
class CrossProjectResumeSameWorktree:
    """跨项目但同一仓库 worktree"""
    project_path: str
    is_cross_project: bool = field(default=True, init=False)
    is_same_repo_worktree: bool = field(default=True, init=False)


@dataclass
class CrossProjectResumeDifferentProject:
    """跨项目且不同仓库"""
    command: str
    project_path: str
    is_cross_project: bool = field(default=True, init=False)
    is_same_repo_worktree: bool = field(default=False, init=False)


CrossProjectResumeResult = Union[
    CrossProjectResumeNotCross,
    CrossProjectResumeSameWorktree,
    CrossProjectResumeDifferentProject,
]


def _quote_path(path: str) -> str:
    """安全地对路径进行 shell 引用"""
    return shlex.quote(path)


def _get_session_id_str(log: LogOption) -> Optional[str]:
    """从日志中提取 session ID 字符串"""
    # 延迟导入避免循环依赖
    try:
        from .session_storage import get_session_id_from_log
        sid = get_session_id_from_log(log)
        return str(sid) if sid is not None else None
    except (ImportError, Exception):
        # 降级：直接从字典中取
        sid = log.get("session_id") or log.get("sessionId")
        return str(sid) if sid is not None else None


def check_cross_project_resume(
    log: LogOption,
    show_all_projects: bool,
    worktree_paths: List[str],
) -> CrossProjectResumeResult:
    """检查日志是否来自不同项目目录，并判断跨项目恢复策略。

    对于同一仓库的 worktree，可直接恢复无需 cd。
    对于不同项目，生成包含 cd 命令的恢复指令。

    Args:
        log: 日志对象，包含 projectPath 等元数据
        show_all_projects: 是否显示所有项目的日志
        worktree_paths: 当前仓库所有 worktree 路径列表

    Returns:
        CrossProjectResumeResult 联合类型之一
    """
    # 延迟导入避免循环依赖
    try:
        from ..bootstrap.state import get_original_cwd
        current_cwd = get_original_cwd()
    except (ImportError, Exception):
        current_cwd = os.getcwd()

    log_project_path: Optional[str] = log.get("projectPath") or log.get("project_path")

    # 如果不展示所有项目，或日志没有项目路径，或路径与当前相同 → 非跨项目
    if not show_all_projects or not log_project_path or log_project_path == current_cwd:
        return CrossProjectResumeNotCross()

    user_type = os.environ.get("USER_TYPE", "")

    # 非 ant 用户不做 worktree 检测，直接生成 cd 命令
    if user_type != "ant":
        session_id = _get_session_id_str(log)
        command = f"cd {_quote_path(log_project_path)} && claude --resume {session_id}"
        return CrossProjectResumeDifferentProject(
            command=command,
            project_path=log_project_path,
        )

    # 检查 log.projectPath 是否在同一仓库的 worktree 下
    sep = os.sep
    is_same_repo = any(
        log_project_path == wt or log_project_path.startswith(wt + sep)
        for wt in worktree_paths
    )

    if is_same_repo:
        return CrossProjectResumeSameWorktree(project_path=log_project_path)

    # 不同仓库 → 生成 cd 命令
    session_id = _get_session_id_str(log)
    command = f"cd {_quote_path(log_project_path)} && claude --resume {session_id}"
    return CrossProjectResumeDifferentProject(
        command=command,
        project_path=log_project_path,
    )
