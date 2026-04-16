"""
Shell execution utilities
原始 TS: src/utils/Shell.ts (core exec function)

execa/child_process → asyncio.subprocess
"""
from __future__ import annotations

import asyncio
import os
import shlex
import signal
from typing import Optional

from claude_code.utils.shell_command import ExecResult

DEFAULT_TIMEOUT_MS = 30 * 60 * 1000  # 30 minutes


async def find_suitable_shell() -> str:
    """
    Determines the best available shell to use.
    原始 TS: findSuitableShell
    """
    # Check for explicit shell override first
    shell_override = os.environ.get("CLAUDE_CODE_SHELL")
    if shell_override:
        if os.path.isfile(shell_override) and os.access(shell_override, os.X_OK):
            return shell_override

    # Try common shells in order
    for shell in ["/bin/bash", "/usr/bin/bash", "/bin/zsh", "/usr/bin/zsh", "/bin/sh"]:
        if os.path.isfile(shell) and os.access(shell, os.X_OK):
            return shell

    return "/bin/sh"


async def exec_command(
    command: str,
    *,
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    shell: Optional[str] = None,
    stdin_data: Optional[str] = None,
) -> ExecResult:
    """
    Execute a shell command and return the result.
    原始 TS: exec() in Shell.ts
    """
    shell_path = shell or await find_suitable_shell()
    timeout_s = timeout_ms / 1000.0

    exec_env = {**os.environ, **(env or {})}

    try:
        proc = await asyncio.create_subprocess_exec(
            shell_path,
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_data else None,
            cwd=cwd,
            env=exec_env,
        )

        stdin_bytes = stdin_data.encode() if stdin_data else None

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes),
                timeout=timeout_s,
            )
            return ExecResult(
                stdout=stdout_b.decode(errors="replace"),
                stderr=stderr_b.decode(errors="replace"),
                code=proc.returncode or 0,
                interrupted=False,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                stdout_b, stderr_b = await proc.communicate()
            except Exception:
                stdout_b, stderr_b = b"", b""
            return ExecResult(
                stdout=stdout_b.decode(errors="replace"),
                stderr=stderr_b.decode(errors="replace"),
                code=proc.returncode or -1,
                interrupted=True,
            )
    except FileNotFoundError as e:
        return ExecResult(
            stdout="",
            stderr=str(e),
            code=127,
            interrupted=False,
            pre_spawn_error=str(e),
        )
