"""Sandbox adapter. Ported from utils/sandbox/sandbox-adapter.ts"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SandboxConfig:
    """Configuration for the sandbox runtime."""

    image: Optional[str] = None
    memory_limit_mb: int = 512
    cpu_limit: float = 1.0
    timeout_s: float = 60.0
    env: Dict[str, str] = field(default_factory=dict)
    mounts: List[Dict[str, str]] = field(default_factory=list)
    network_enabled: bool = False


@dataclass
class SandboxResult:
    """Result from a sandbox command execution."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    error: Optional[str] = None


def _is_sandbox_enabled() -> bool:
    """Return True if the sandbox runtime should be used."""
    return os.environ.get("CLAUDE_CODE_SANDBOX") == "1"


class SandboxManager:
    """Manages sandbox runtime for isolated command execution.

    This is a Python port of the TypeScript sandbox adapter that wraps the
    ``@anthropic-ai/sandbox-runtime`` package. On platforms where the sandbox
    runtime is unavailable, commands fall back to direct execution.
    """

    _instance: Optional["SandboxManager"] = None

    def __init__(self) -> None:
        self._config: SandboxConfig = SandboxConfig()
        self._active = False

    @classmethod
    def get_instance(cls) -> "SandboxManager":
        """Return the global singleton SandboxManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def configure(self, config: SandboxConfig) -> None:
        """Update the sandbox configuration."""
        self._config = config

    def is_sandbox_active(self) -> bool:
        """Return True if the sandbox is currently active."""
        return self._active and _is_sandbox_enabled()

    async def start(self) -> bool:
        """Attempt to start the sandbox runtime.

        Returns True on success, False if the sandbox is unavailable.
        """
        if not _is_sandbox_enabled():
            return False
        try:
            # Attempt to import the sandbox runtime library
            # (not yet available in the Python port)
            import claude_code._sandbox_runtime as _sr  # type: ignore[import]

            self._active = True
            return True
        except ImportError:
            self._active = False
            return False

    async def stop(self) -> None:
        """Stop the sandbox runtime."""
        self._active = False

    async def run_in_sandbox(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> SandboxResult:
        """Execute a shell command, optionally inside the sandbox.

        Falls back to direct execution when the sandbox is not active.

        Args:
            command: Shell command string to execute.
            cwd: Working directory. Defaults to the current directory.
            env: Additional environment variables (merged with current env).
            timeout: Override timeout in seconds. Uses the configured default if None.
            **kwargs: Additional keyword arguments forwarded to the subprocess.

        Returns:
            A :class:`SandboxResult` containing stdout, stderr, and exit code.
        """
        effective_timeout = timeout or self._config.timeout_s
        effective_env = {**os.environ, **(self._config.env), **(env or {})}

        if self.is_sandbox_active():
            return await self._run_sandboxed(
                command, cwd=cwd, env=effective_env, timeout=effective_timeout
            )

        return await self._run_direct(
            command, cwd=cwd, env=effective_env, timeout=effective_timeout
        )

    async def _run_direct(
        self,
        command: str,
        cwd: Optional[str],
        env: Dict[str, str],
        timeout: float,
    ) -> SandboxResult:
        """Run a command directly via asyncio subprocess (no sandbox)."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                return SandboxResult(
                    exit_code=proc.returncode or 0,
                    stdout=stdout_bytes.decode("utf-8", errors="replace"),
                    stderr=stderr_bytes.decode("utf-8", errors="replace"),
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return SandboxResult(
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    timed_out=True,
                    error=f"Command timed out after {timeout}s",
                )
        except Exception as exc:
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr="",
                error=str(exc),
            )

    async def _run_sandboxed(
        self,
        command: str,
        cwd: Optional[str],
        env: Dict[str, str],
        timeout: float,
    ) -> SandboxResult:
        """Run a command inside the sandbox runtime.

        Not yet fully implemented in the Python port; falls back to direct execution.
        """
        return await self._run_direct(command, cwd=cwd, env=env, timeout=timeout)
