"""
shell_provider.py - Abstract shell provider interface.

Port of TypeScript shellProvider.ts.
"""

import asyncio
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ShellExecutionResult:
    """Result from a shell command execution."""

    def __init__(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        interrupted: bool = False,
        new_cwd: Optional[str] = None,
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.interrupted = interrupted
        self.new_cwd = new_cwd


class ShellProvider(ABC):
    """Abstract base class for shell providers."""

    type: str = 'unknown'
    detached: bool = False
    shell_path: str = '/bin/sh'

    @abstractmethod
    async def build_exec_command(
        self,
        command: str,
        opts: Dict[str, Any],
    ) -> Dict[str, str]:
        """
        Build the execution command string.

        Returns:
            Dict with 'commandString' and 'cwdFilePath' keys.
        """
        ...

    @abstractmethod
    def get_spawn_args(self, command_string: str) -> List[str]:
        """
        Get the arguments to pass to the shell for the command.

        Returns:
            List of shell arguments.
        """
        ...

    @abstractmethod
    async def get_environment_overrides(self, command: str) -> Dict[str, str]:
        """
        Get environment variable overrides for the command.

        Returns:
            Dict of environment variables.
        """
        ...

    async def execute(
        self,
        command: str,
        opts: Dict[str, Any],
        cwd: Optional[str] = None,
    ) -> ShellExecutionResult:
        """
        Execute a command using this shell provider.

        Args:
            command: The command to execute
            opts: Execution options
            cwd: Working directory

        Returns:
            ShellExecutionResult with output and exit code.
        """
        try:
            exec_cmd = await self.build_exec_command(command, opts)
            command_string = exec_cmd['commandString']
            cwd_file_path = exec_cmd.get('cwdFilePath')

            spawn_args = self.get_spawn_args(command_string)
            env_overrides = await self.get_environment_overrides(command)

            env = {**os.environ, **env_overrides}

            timeout = opts.get('timeout', 300)
            abort_signal = opts.get('abortSignal')

            # Build full command
            full_cmd = [self.shell_path] + spawn_args

            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            interrupted = False
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                stdout_bytes, stderr_bytes = await proc.communicate()
                interrupted = True
            except asyncio.CancelledError:
                proc.kill()
                stdout_bytes, stderr_bytes = await proc.communicate()
                interrupted = True

            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            exit_code = proc.returncode or 0

            # Read new cwd if available
            new_cwd = None
            if cwd_file_path:
                try:
                    from pathlib import Path
                    new_cwd = Path(cwd_file_path).read_text('utf-8').strip()
                    Path(cwd_file_path).unlink(missing_ok=True)
                except Exception:
                    pass

            return ShellExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                interrupted=interrupted,
                new_cwd=new_cwd,
            )

        except Exception as e:
            logger.error(f'Shell execution failed: {e}')
            return ShellExecutionResult(
                stdout='',
                stderr=str(e),
                exit_code=1,
            )
