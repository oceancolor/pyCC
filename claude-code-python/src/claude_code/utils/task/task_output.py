"""Task output class (single source of truth). Ported from utils/task/TaskOutput.ts"""

from __future__ import annotations

import asyncio
import threading
from typing import Callable, Dict, List, Optional

from .disk_output import DiskTaskOutput, get_task_output_delta

DEFAULT_MAX_MEMORY = 8 * 1024 * 1024  # 8 MB
POLL_INTERVAL_MS = 1000
PROGRESS_TAIL_BYTES = 4096

ProgressCallback = Callable[[str, str, int, int, bool], None]


class _CircularBuffer(List[str]):
    """Fixed-size circular buffer for the most-recent lines."""

    def __init__(self, capacity: int) -> None:
        super().__init__()
        self._capacity = capacity

    def push(self, item: str) -> None:
        if len(self) >= self._capacity:
            self.pop(0)
        self.append(item)


class TaskOutput:
    """Single source of truth for a task's stdout/stderr.

    File mode (bash): output goes directly to a file via stdio redirection;
    Python never sees the bytes. Progress is extracted by polling the file.

    Pipe mode (hooks): data flows through write_stdout()/write_stderr() and
    is buffered in memory, spilling to disk if it exceeds the limit.
    """

    # Class-level registry for file-mode polling
    _registry: Dict[str, "TaskOutput"] = {}
    _active_polling: Dict[str, "TaskOutput"] = {}
    _poll_interval: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    def __init__(
        self,
        task_id: str,
        on_progress: Optional[ProgressCallback] = None,
        stdout_to_file: bool = False,
        max_memory: int = DEFAULT_MAX_MEMORY,
    ) -> None:
        self.task_id = task_id
        self.path = f"/tmp/claude-task-{task_id}.output"
        self.stdout_to_file = stdout_to_file

        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._disk: Optional[DiskTaskOutput] = None
        self._recent_lines = _CircularBuffer(1000)
        self._total_lines = 0
        self._total_bytes = 0
        self._max_memory = max_memory
        self._on_progress = on_progress
        self._output_file_redundant = False
        self._output_file_size = 0
        self._file_offset = 0

    # -------------------------------------------------------------------------
    # Write-side API (pipe mode only)
    # -------------------------------------------------------------------------

    def write_stdout(self, data: str) -> None:
        """Append stdout data to the in-memory buffer."""
        self._stdout_buffer += data
        lines = data.splitlines()
        for line in lines:
            self._recent_lines.push(line)
        self._total_lines += len(lines)
        self._total_bytes += len(data.encode())
        if self._on_progress:
            self._fire_progress()

    def write_stderr(self, data: str) -> None:
        """Append stderr data (interleaved with stdout for display purposes)."""
        self.write_stdout(data)

    # -------------------------------------------------------------------------
    # Read-side API
    # -------------------------------------------------------------------------

    def get_stdout(self) -> str:
        """Return all buffered stdout content."""
        if self.stdout_to_file:
            try:
                with open(self.path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                    self._output_file_redundant = True
                    self._output_file_size = len(content.encode())
                    return content
            except FileNotFoundError:
                return ""
        return self._stdout_buffer

    def get_stderr(self) -> str:
        """Return buffered stderr. Always '' in file mode (interleaved in file)."""
        if self.stdout_to_file:
            return ""
        return self._stderr_buffer

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def total_lines(self) -> int:
        return self._total_lines

    # -------------------------------------------------------------------------
    # Polling (file mode)
    # -------------------------------------------------------------------------

    def _fire_progress(self) -> None:
        if not self._on_progress:
            return
        recent = "\n".join(self._recent_lines[-20:])
        all_content = self.get_stdout()
        is_incomplete = False
        self._on_progress(recent, all_content, self._total_lines, self._total_bytes, is_incomplete)

    def start_polling(self) -> None:
        """Start polling the output file for new data (file mode only)."""
        if not self.stdout_to_file or not self._on_progress:
            return
        TaskOutput._registry[self.task_id] = self
        TaskOutput._active_polling[self.task_id] = self
        TaskOutput._ensure_poll_loop()

    def stop_polling(self) -> None:
        """Stop polling for this task."""
        TaskOutput._active_polling.pop(self.task_id, None)
        TaskOutput._registry.pop(self.task_id, None)

    @classmethod
    def _ensure_poll_loop(cls) -> None:
        """Ensure the shared polling loop is running."""
        if cls._poll_interval is not None:
            return
        try:
            loop = asyncio.get_event_loop()
            cls._poll_interval = loop.create_task(cls._poll_loop())
        except RuntimeError:
            pass

    @classmethod
    async def _poll_loop(cls) -> None:
        while True:
            await asyncio.sleep(POLL_INTERVAL_MS / 1000)
            for task_output in list(cls._active_polling.values()):
                try:
                    new_data, new_offset = get_task_output_delta(
                        task_output.task_id, task_output._file_offset
                    )
                    if new_data:
                        task_output._file_offset = new_offset
                        task_output._total_bytes += len(new_data.encode())
                        lines = new_data.splitlines()
                        task_output._total_lines += len(lines)
                        for line in lines:
                            task_output._recent_lines.push(line)
                        task_output._fire_progress()
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    async def cleanup(self) -> None:
        """Remove the task output file from disk."""
        self.stop_polling()
        if self._disk:
            await self._disk.cleanup()
        else:
            import os

            try:
                os.unlink(self.path)
            except Exception:
                pass
