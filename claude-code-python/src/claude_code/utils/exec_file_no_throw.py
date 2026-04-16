"""
Execute subprocess without throwing exceptions.

Provides exec_file_no_throw() which always resolves with
(stdout, stderr, exit_code) rather than raising on non-zero exit.
"""

import asyncio
import os
import signal
from dataclasses import dataclass
from typing import Optional

_SECONDS_IN_MINUTE = 60
_MS_IN_SECOND = 1000
_DEFAULT_TIMEOUT_S = 10 * _SECONDS_IN_MINUTE  # 600s


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    code: int
    error: Optional[str] = None


async def exec_file_no_throw(
    file: str,
    args: list[str],
    *,
    timeout: Optional[float] = _DEFAULT_TIMEOUT_S,
    preserve_output_on_error: bool = True,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    stdin_data: Optional[str] = None,
) -> ExecResult:
    """
    Run *file* with *args* as a subprocess. Never raises; always returns ExecResult.

    Args:
        file: Executable path or name.
        args: Argument list (not including the executable itself).
        timeout: Seconds before the process is killed (default 600).
        preserve_output_on_error: When True, stdout/stderr are kept on failure.
        cwd: Working directory for the subprocess.
        env: Environment variables override (None = inherit).
        stdin_data: Optional string piped to the process stdin.

    Returns:
        ExecResult with stdout, stderr, code, and optional error description.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            file,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
            cwd=cwd,
            env={**os.environ, **(env or {})} if env else None,
        )

        stdin_bytes = stdin_data.encode() if stdin_data is not None else None

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(stdin_bytes), timeout=timeout
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            stdout_b, stderr_b = b"", b""
            return ExecResult(
                stdout="" if not preserve_output_on_error else stdout_b.decode(errors="replace"),
                stderr="" if not preserve_output_on_error else stderr_b.decode(errors="replace"),
                code=-(signal.SIGKILL),
                error=f"Process timed out after {timeout}s",
            )

        stdout = stdout_b.decode(errors="replace")
        stderr = stderr_b.decode(errors="replace")
        code = proc.returncode if proc.returncode is not None else 1

        if code != 0:
            error_msg = _build_error_message(code, stderr)
            if preserve_output_on_error:
                return ExecResult(stdout=stdout, stderr=stderr, code=code, error=error_msg)
            return ExecResult(stdout="", stderr="", code=code, error=error_msg)

        return ExecResult(stdout=stdout, stderr=stderr, code=0)

    except FileNotFoundError as exc:
        return ExecResult(stdout="", stderr="", code=1, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return ExecResult(stdout="", stderr="", code=1, error=str(exc))


def exec_file_no_throw_sync(
    file: str,
    args: list[str],
    *,
    timeout: Optional[float] = _DEFAULT_TIMEOUT_S,
    preserve_output_on_error: bool = True,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    stdin_data: Optional[str] = None,
) -> ExecResult:
    """Synchronous wrapper around exec_file_no_throw using subprocess.run."""
    import subprocess

    try:
        merged_env = {**os.environ, **(env or {})} if env else None
        result = subprocess.run(
            [file, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=merged_env,
            input=stdin_data,
        )
        code = result.returncode
        if code != 0:
            error_msg = _build_error_message(code, result.stderr)
            if preserve_output_on_error:
                return ExecResult(
                    stdout=result.stdout, stderr=result.stderr,
                    code=code, error=error_msg,
                )
            return ExecResult(stdout="", stderr="", code=code, error=error_msg)
        return ExecResult(stdout=result.stdout, stderr=result.stderr, code=0)
    except subprocess.TimeoutExpired:
        return ExecResult(stdout="", stderr="", code=1, error=f"Timed out after {timeout}s")
    except FileNotFoundError as exc:
        return ExecResult(stdout="", stderr="", code=1, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return ExecResult(stdout="", stderr="", code=1, error=str(exc))


def _build_error_message(code: int, stderr: str) -> str:
    if stderr:
        return stderr.strip()
    return str(code)
