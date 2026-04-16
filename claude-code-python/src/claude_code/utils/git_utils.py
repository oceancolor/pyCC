# 原始 TS: utils/gitUtils.ts (扩展 git.py)
"""Git 工具扩展（状态、提交、分支操作）"""
from __future__ import annotations
import subprocess
from typing import List, Optional
from .exec_no_throw import exec_no_throw, exec_sync


def git_status(cwd: Optional[str] = None) -> str:
    return exec_sync(["git", "status", "--short"], cwd=cwd)


def git_diff(cwd: Optional[str] = None, staged: bool = False) -> str:
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--cached")
    r = exec_no_throw(cmd, cwd=cwd)
    return r.stdout


def git_log(n: int = 10, cwd: Optional[str] = None) -> str:
    return exec_sync(
        ["git", "log", f"--oneline", f"-{n}"], cwd=cwd
    )


def git_add(paths: List[str], cwd: Optional[str] = None) -> bool:
    r = exec_no_throw(["git", "add"] + paths, cwd=cwd)
    return r.ok


def git_commit(message: str, cwd: Optional[str] = None) -> bool:
    r = exec_no_throw(["git", "commit", "-m", message], cwd=cwd)
    return r.ok


def git_current_branch(cwd: Optional[str] = None) -> str:
    return exec_sync(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)


def git_stash(cwd: Optional[str] = None) -> bool:
    return exec_no_throw(["git", "stash"], cwd=cwd).ok


def git_stash_pop(cwd: Optional[str] = None) -> bool:
    return exec_no_throw(["git", "stash", "pop"], cwd=cwd).ok
