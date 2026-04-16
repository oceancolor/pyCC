"""
graceful_shutdown.py - Python port of gracefulShutdown.ts
Source: claude-code-analysis/claude-code-source/utils/gracefulShutdown.ts

Core functionality:
- Process signal handling (SIGINT / SIGTERM / SIGHUP)
- Graceful exit mechanism with configurable timeout
- Cleanup callback registration
- Failsafe timer to guarantee exit even if cleanup hangs
"""

import asyncio
import os
import signal
import sys
import threading
from typing import Callable, Coroutine, List, Optional

# ---------------------------------------------------------------------------
# Cleanup registry
# ---------------------------------------------------------------------------

_cleanup_functions: List[Callable[[], Coroutine]] = []


def register_cleanup_function(fn: Callable[[], Coroutine]) -> None:
    """Register an async cleanup function to be called during shutdown."""
    _cleanup_functions.append(fn)


def deregister_cleanup_function(fn: Callable[[], Coroutine]) -> None:
    """Deregister a previously registered cleanup function."""
    try:
        _cleanup_functions.remove(fn)
    except ValueError:
        pass


async def run_cleanup_functions() -> None:
    """Run all registered cleanup functions, ignoring individual errors."""
    for fn in list(_cleanup_functions):
        try:
            await fn()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level shutdown state
# ---------------------------------------------------------------------------

_shutdown_in_progress: bool = False
_failsafe_timer: Optional[threading.Timer] = None
_pending_shutdown: Optional[asyncio.Task] = None


def is_shutting_down() -> bool:
    """Check if graceful shutdown is in progress."""
    return _shutdown_in_progress


def reset_shutdown_state() -> None:
    """Reset shutdown state — only for use in tests."""
    global _shutdown_in_progress, _failsafe_timer, _pending_shutdown
    _shutdown_in_progress = False
    if _failsafe_timer is not None:
        _failsafe_timer.cancel()
        _failsafe_timer = None
    _pending_shutdown = None


def get_pending_shutdown_for_testing() -> Optional[asyncio.Task]:
    """Returns the in-flight shutdown task, if any. Only for use in tests."""
    return _pending_shutdown


# ---------------------------------------------------------------------------
# Terminal cleanup
# ---------------------------------------------------------------------------

def cleanup_terminal_modes() -> None:
    """
    Clean up terminal modes before process exit.
    Python equivalent: restore terminal to sane state.
    In a TTY-less environment, this is a no-op.
    """
    if not sys.stdout.isatty():
        return
    try:
        import termios
        fd = sys.stdout.fileno()
        attrs = termios.tcgetattr(fd)
        # Reset to sane defaults - enable echo, canonical mode
        attrs[3] |= termios.ECHO | termios.ICANON  # type: ignore[index]
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Force exit
# ---------------------------------------------------------------------------

def force_exit(exit_code: int = 0) -> None:
    """
    Force process exit, handling edge cases.
    Falls back to SIGKILL if normal exit fails.
    """
    global _failsafe_timer
    if _failsafe_timer is not None:
        _failsafe_timer.cancel()
        _failsafe_timer = None

    try:
        sys.exit(exit_code)
    except SystemExit:
        raise
    except Exception:
        os.kill(os.getpid(), signal.SIGKILL)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

# Default session-end hook timeout (ms)
_SESSION_END_HOOK_TIMEOUT_MS = 1500
_FAILSAFE_BASE_MS = 5000


async def graceful_shutdown(
    exit_code: int = 0,
    reason: str = "other",
    final_message: Optional[str] = None,
    cleanup_timeout_s: float = 2.0,
    analytics_timeout_s: float = 0.5,
) -> None:
    """
    Async graceful shutdown function that drains the event loop.

    Steps:
    1. Set failsafe timer to guarantee exit
    2. Run cleanup functions (with timeout)
    3. Flush analytics (with timeout)
    4. Force exit

    Args:
        exit_code: The process exit code.
        reason: The reason for shutdown (informational).
        final_message: Optional message to print to stderr before exit.
        cleanup_timeout_s: Maximum seconds to wait for cleanup functions.
        analytics_timeout_s: Maximum seconds to wait for analytics flush.
    """
    global _shutdown_in_progress, _failsafe_timer

    if _shutdown_in_progress:
        return
    _shutdown_in_progress = True

    # Arm failsafe timer: guarantees exit even if cleanup hangs
    failsafe_delay_s = max(
        _FAILSAFE_BASE_MS / 1000,
        (_SESSION_END_HOOK_TIMEOUT_MS + 3500) / 1000,
    )

    def _failsafe() -> None:
        cleanup_terminal_modes()
        os._exit(exit_code)  # hard exit bypassing Python cleanup

    _failsafe_timer = threading.Timer(failsafe_delay_s, _failsafe)
    _failsafe_timer.daemon = True
    _failsafe_timer.start()

    # Cleanup terminal
    cleanup_terminal_modes()

    # Run registered cleanup functions with timeout
    try:
        await asyncio.wait_for(run_cleanup_functions(), timeout=cleanup_timeout_s)
    except (asyncio.TimeoutError, Exception):
        pass

    # Flush analytics (placeholder — subclasses can override)
    try:
        await asyncio.sleep(min(analytics_timeout_s, 0.1))
    except Exception:
        pass

    # Print final message to stderr if provided
    if final_message:
        try:
            sys.stderr.write(final_message + "\n")
            sys.stderr.flush()
        except Exception:
            pass

    force_exit(exit_code)


def graceful_shutdown_sync(
    exit_code: int = 0,
    reason: str = "other",
    final_message: Optional[str] = None,
) -> None:
    """
    Synchronous wrapper that schedules graceful_shutdown in the event loop.
    If no event loop is running, starts one.
    """
    global _pending_shutdown

    try:
        loop = asyncio.get_running_loop()
        # Schedule it as a task; it will run on next iteration
        _pending_shutdown = loop.create_task(
            graceful_shutdown(exit_code, reason, final_message)
        )
    except RuntimeError:
        # No running event loop — run in a new one
        asyncio.run(graceful_shutdown(exit_code, reason, final_message))


# ---------------------------------------------------------------------------
# Setup global signal handlers
# ---------------------------------------------------------------------------

_handlers_installed: bool = False


def setup_graceful_shutdown() -> None:
    """
    Set up global signal handlers for graceful shutdown.
    Idempotent: safe to call multiple times.
    """
    global _handlers_installed
    if _handlers_installed:
        return
    _handlers_installed = True

    def _make_signal_handler(sig_exit_code: int, sig_name: str):
        def _handler(signum, frame):
            # Avoid re-entering if already shutting down
            if _shutdown_in_progress:
                return
            graceful_shutdown_sync(sig_exit_code, reason=sig_name)
        return _handler

    # SIGINT → exit code 0 (Ctrl-C, user-initiated)
    signal.signal(signal.SIGINT, _make_signal_handler(0, "SIGINT"))

    # SIGTERM → exit code 143 (128 + 15)
    signal.signal(signal.SIGTERM, _make_signal_handler(143, "SIGTERM"))

    # SIGHUP (Unix only) → exit code 129 (128 + 1)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _make_signal_handler(129, "SIGHUP"))  # type: ignore[attr-defined]

    # Log uncaught exceptions
    def _uncaught_exception_handler(exc_type, exc_value, exc_tb):
        import traceback
        try:
            sys.stderr.write(
                f"[graceful_shutdown] Uncaught exception: {exc_type.__name__}: {exc_value}\n"
            )
            traceback.print_tb(exc_tb, file=sys.stderr)
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _uncaught_exception_handler
