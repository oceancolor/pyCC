"""
Process utilities - Python port of process.ts

Avoids name collision with stdlib 'process' module by using process_utils.py.

Provides:
- register_process_output_error_handlers() - EPIPE guard for stdout/stderr
- write_to_stdout(data) / write_to_stderr(data)  - safe write helpers
- exit_with_error(message) → NoReturn
- peek_for_stdin_data(stream, ms) → bool  (True = timed out, no data)
"""
from __future__ import annotations

import asyncio
import io
import signal
import sys
from typing import Any


# ---------------------------------------------------------------------------
# EPIPE guard
# ---------------------------------------------------------------------------

def _handle_epipe() -> None:
    """Suppress BrokenPipeError on stdout/stderr (equivalent to EPIPE guard)."""
    # Python raises BrokenPipeError (EPIPE) when the read end of a pipe closes.
    # Install a SIGPIPE handler that exits silently (Unix only).
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def register_process_output_error_handlers() -> None:
    """Register EPIPE / BrokenPipeError guards for stdout and stderr.

    Call once at process startup (mirrors registerProcessOutputErrorHandlers).
    """
    _handle_epipe()


# ---------------------------------------------------------------------------
# Safe write helpers
# ---------------------------------------------------------------------------

def _write_out(stream: io.TextIOWrapper, data: str) -> None:
    try:
        stream.write(data)
        stream.flush()
    except BrokenPipeError:
        # Pipe closed; nothing we can do
        pass
    except OSError:
        pass


def write_to_stdout(data: str) -> None:
    _write_out(sys.stdout, data)


def write_to_stderr(data: str) -> None:
    _write_out(sys.stderr, data)


# ---------------------------------------------------------------------------
# Exit helper
# ---------------------------------------------------------------------------

def exit_with_error(message: str) -> None:  # type: ignore[return]
    """Write message to stderr and raise SystemExit(1)."""
    print(message, file=sys.stderr)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Stdin peek
# ---------------------------------------------------------------------------

async def peek_for_stdin_data(
    reader: asyncio.StreamReader,
    ms: int,
) -> bool:
    """Wait for the first data chunk on *reader* or timeout after *ms* ms.

    Returns True if timed out (no data), False if data arrived.
    Used by -p mode to distinguish a real pipe producer from an idle stdin.
    """
    timeout_s = ms / 1000.0
    try:
        await asyncio.wait_for(reader.read(1), timeout=timeout_s)
        return False  # got data
    except asyncio.TimeoutError:
        return True   # timed out
