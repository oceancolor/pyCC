"""Task disk output management. Ported from utils/task/diskOutput.ts"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional


def get_task_output_path(task_id: str) -> str:
    """Return the path to the disk-backed output file for a task.

    The file lives in the system temp directory using a stable name derived
    from the task ID, so multiple processes can locate the same file.
    """
    return os.path.join(tempfile.gettempdir(), f"claude-task-{task_id}.output")


def get_task_output_delta(task_id: str, offset: int) -> tuple[str, int]:
    """Read new output from the task output file starting at ``offset``.

    Args:
        task_id: The task identifier.
        offset: Byte offset to start reading from.

    Returns:
        A tuple ``(new_content, new_offset)`` where ``new_offset`` is the
        updated byte position. Returns ``("", offset)`` if the file doesn't
        exist or no new data is available.
    """
    path = get_task_output_path(task_id)
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
            if not data:
                return ("", offset)
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = repr(data)
            return (text, offset + len(data))
    except FileNotFoundError:
        return ("", offset)
    except Exception:
        return ("", offset)


class DiskTaskOutput:
    """Manages disk-backed output for a task (file mode).

    In file mode stdout/stderr from the subprocess are written directly to disk
    by the OS (via stdio fd redirection) rather than piped through Python.
    This class handles creation and cleanup of the output file.
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.path = get_task_output_path(task_id)
        self._file: Optional[object] = None

    async def open(self) -> None:
        """Create (and truncate) the output file, ensuring the parent directory exists."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._open_sync)

    def _open_sync(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # Open (create or truncate) so the subprocess can inherit the fd
        self._file = open(self.path, "wb")

    def get_fd(self) -> Optional[int]:
        """Return the underlying file descriptor for subprocess stdio redirection."""
        if self._file is not None:
            return self._file.fileno()  # type: ignore[attr-defined]
        return None

    def close(self) -> None:
        """Close the output file handle (subprocess has already closed its end)."""
        if self._file is not None:
            try:
                self._file.close()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._file = None

    async def cleanup(self) -> None:
        """Delete the output file from disk."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._cleanup_sync)

    def _cleanup_sync(self) -> None:
        self.close()
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        except Exception:
            pass
