"""Stream JSON stdout guard - Python port of streamJsonStdoutGuard.ts.

Prevents stdout pollution in JSON-stream mode by intercepting writes,
buffering until newline, and diverting non-JSON lines to stderr.
"""

from __future__ import annotations

import io
import json
import sys
from typing import Optional

STDOUT_GUARD_MARKER = '[stdout-guard]'


def _is_json_line(line: str) -> bool:
    """Return True if *line* is valid JSON or empty (NDJSON blank separator)."""
    if not line:
        return True
    try:
        json.loads(line)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


class _GuardedStdout(io.RawIOBase):
    """Wraps the real stdout.buffer, filtering non-JSON lines to stderr."""

    def __init__(self, real_stdout: io.TextIOWrapper) -> None:
        self._real = real_stdout
        self._buffer = ''

    def _flush_line(self, line: str) -> None:
        if _is_json_line(line):
            self._real.write(line + '\n')
        else:
            sys.stderr.write(f'{STDOUT_GUARD_MARKER} {line}\n')
            sys.stderr.flush()

    def write_text(self, text: str) -> int:  # type: ignore[override]
        self._buffer += text
        while '\n' in self._buffer:
            idx = self._buffer.index('\n')
            line = self._buffer[:idx]
            self._buffer = self._buffer[idx + 1:]
            self._flush_line(line)
        return len(text)

    def flush_remaining(self) -> None:
        if self._buffer:
            self._flush_line(self._buffer)
            self._buffer = ''

    def flush(self) -> None:
        self._real.flush()


class StreamJsonStdoutGuard:
    """Guard that diverts non-JSON lines from stdout to stderr.

    Usage::

        guard = StreamJsonStdoutGuard()
        guard.enable()
        ...
        guard.disable()
    """

    def __init__(self) -> None:
        self._active = False
        self._original_write = None
        self._guarded: Optional[_GuardedStdout] = None

    @property
    def is_active(self) -> bool:
        return self._active

    def enable(self) -> None:
        """Install the stdout guard. Installing twice is a no-op."""
        if self._active:
            return
        self._active = True
        self._original_write = sys.stdout.write
        self._guarded = _GuardedStdout(sys.stdout)

        guarded = self._guarded

        def _patched_write(text: str) -> int:
            return guarded.write_text(text)

        sys.stdout.write = _patched_write  # type: ignore[method-assign]

    def disable(self) -> None:
        """Remove the guard and flush any buffered content."""
        if not self._active:
            return
        if self._guarded is not None:
            self._guarded.flush_remaining()
        if self._original_write is not None:
            sys.stdout.write = self._original_write  # type: ignore[method-assign]
        self._original_write = None
        self._guarded = None
        self._active = False


# Module-level singleton (mirrors the TS module-level `installed` flag)
_guard = StreamJsonStdoutGuard()


def install_stream_json_stdout_guard() -> None:
    """Install the module-level stdout guard."""
    _guard.enable()


def reset_stream_json_stdout_guard_for_testing() -> None:
    """Testing-only reset — restores real stdout.write."""
    _guard.disable()
