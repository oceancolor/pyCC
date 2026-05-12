"""
sdk_control_transport.py - SDK-controlled MCP transport for stdio servers.

Port of TypeScript SdkControlTransport.ts.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class SdkControlTransport:
    """
    Transport that launches and communicates with an MCP server subprocess.

    Unlike the SDK's built-in StdioClientTransport, this class gives us
    full control over process lifecycle (env, cwd, restart) and exposes
    raw line-level message hooks for logging/telemetry.
    """

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ):
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd

        self._process: Optional[asyncio.subprocess.Process] = None
        self._closed = False

        self._on_message: Optional[Callable[[Dict[str, Any]], None]] = None
        self._on_close: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[Exception], None]] = None

        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None

    def on_message(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Set the message handler."""
        self._on_message = handler

    def on_close(self, handler: Callable[[], None]) -> None:
        """Set the close handler."""
        self._on_close = handler

    def on_error(self, handler: Callable[[Exception], None]) -> None:
        """Set the error handler."""
        self._on_error = handler

    async def start(self) -> None:
        """Start the subprocess and begin reading messages."""
        proc_env = dict(os.environ)
        if self.env:
            proc_env.update(self.env)

        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
                cwd=self.cwd,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to start MCP server '{self.command}': {e}"
            ) from e

        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

        logger.debug(
            f'[MCP] {self.command} started (pid {self._process.pid})'
        )

    async def _read_stdout(self) -> None:
        """Read JSON-RPC messages from stdout."""
        assert self._process and self._process.stdout

        while not self._closed:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break

                line_str = line.decode('utf-8', errors='replace').rstrip()
                if not line_str:
                    continue

                try:
                    message = json.loads(line_str)
                    if self._on_message:
                        self._on_message(message)
                except json.JSONDecodeError:
                    logger.debug(f'[MCP] non-JSON from {self.command}: {line_str[:200]}')

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._closed:
                    logger.warning(f'[MCP] stdout read error from {self.command}: {e}')
                    if self._on_error:
                        self._on_error(e)
                break

        if not self._closed:
            await self.close()

    async def _read_stderr(self) -> None:
        """Read stderr and log it."""
        assert self._process and self._process.stderr

        while not self._closed:
            try:
                line = await self._process.stderr.readline()
                if not line:
                    break
                msg = line.decode('utf-8', errors='replace').rstrip()
                if msg:
                    logger.debug(f'[MCP stderr] {self.command}: {msg}')
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def send(self, message: Dict[str, Any]) -> None:
        """Send a JSON-RPC message to the server."""
        if self._closed:
            raise RuntimeError('Transport is closed')
        if not self._process or not self._process.stdin:
            raise RuntimeError('Process not started')

        try:
            line = json.dumps(message, ensure_ascii=False) + '\n'
            self._process.stdin.write(line.encode('utf-8'))
            await self._process.stdin.drain()
        except Exception as e:
            raise RuntimeError(f'Failed to send message: {e}') from e

    async def close(self) -> None:
        """Terminate the subprocess and clean up."""
        if self._closed:
            return

        self._closed = True
        logger.debug(f'[MCP] closing {self.command}')

        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except Exception as e:
                logger.debug(f'[MCP] close error for {self.command}: {e}')

        for task in (self._reader_task, self._stderr_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._on_close:
            self._on_close()
