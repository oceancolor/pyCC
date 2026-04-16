# 原始 TS: utils/execFileNoThrow.ts / utils/execSyncWrapper.ts
"""subprocess 封装（不抛异常版本）"""
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Union


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def exec_no_throw(
    cmd: Union[str, List[str]],
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
    input: Optional[str] = None,
    env: Optional[dict] = None,
) -> ExecResult:
    """执行命令，不抛异常，返回 ExecResult"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout,
            input=input,
            capture_output=True,
            text=True,
            shell=isinstance(cmd, str),
            env=env,
        )
        return ExecResult(result.stdout, result.stderr, result.returncode)
    except subprocess.TimeoutExpired:
        return ExecResult("", "timeout", 124)
    except FileNotFoundError as e:
        return ExecResult("", str(e), 127)
    except Exception as e:
        return ExecResult("", str(e), 1)


def exec_sync(cmd: Union[str, List[str]], cwd: Optional[str] = None) -> str:
    """同步执行，返回 stdout 字符串，失败返回空串"""
    r = exec_no_throw(cmd, cwd=cwd)
    return r.stdout.strip() if r.ok else ""
