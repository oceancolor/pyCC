"""
Team Memory File Watcher

Watches the team memory directory for changes and triggers
a debounced push to the server when files are modified.
Performs an initial pull on startup, then starts a directory-level
watchdog (or asyncio polling) watch so first-time writes to a fresh
repo get picked up.

Mirrors watcher.ts from the TypeScript source.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent

    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False

from claude_code.memdir.team_mem_paths import (
    get_team_mem_path,
    is_team_memory_enabled,
)
from claude_code.utils.cleanup_registry import register_cleanup
from claude_code.utils.debug import log_for_debugging
from claude_code.utils.errors import error_message
from claude_code.utils.git import get_github_repo
from claude_code.services.analytics import log_event
from claude_code.services.teamMemorySync import (
    create_sync_state,
    is_team_memory_sync_available,
    pull_team_memory,
    push_team_memory,
    SyncState,
)
from claude_code.services.teamMemorySync.types import TeamMemorySyncPushResult

DEBOUNCE_S = 2.0  # Wait 2s after last change before pushing

# Feature flag — mirrors `feature('TEAMMEM')` in TypeScript.
# Set env var TEAMMEM=1 (or TEAMMEM=true) to enable.
_FEATURE_TEAMMEM = os.environ.get("TEAMMEM", "").lower() in ("1", "true", "yes")

# ─── Watcher state ──────────────────────────────────────────

_observer: Optional[object] = None          # watchdog Observer (if available)
_debounce_task: Optional[asyncio.Task] = None
_push_in_progress: bool = False
_has_pending_changes: bool = False
_current_push_task: Optional[asyncio.Task] = None
_watcher_started: bool = False
_push_suppressed_reason: Optional[str] = None
_sync_state: Optional[SyncState] = None

# asyncio event loop reference for thread-safe scheduling from watchdog
_loop: Optional[asyncio.AbstractEventLoop] = None


def is_permanent_failure(r: TeamMemorySyncPushResult) -> bool:
    """
    Permanent = retry without user action will fail the same way.
    - no_oauth / no_repo: pre-request client checks, no status code
    - 4xx except 409/429: client error
    """
    if r.error_type in ("no_oauth", "no_repo"):
        return True
    if (
        r.http_status is not None
        and 400 <= r.http_status < 500
        and r.http_status not in (409, 429)
    ):
        return True
    return False


async def _execute_push() -> None:
    """
    Execute the push and track its lifecycle.
    Push is read-only on disk (delta+probe, no merge writes).
    """
    global _push_in_progress, _has_pending_changes, _current_push_task
    global _push_suppressed_reason

    if not _sync_state:
        return

    _push_in_progress = True
    try:
        result = await push_team_memory(_sync_state)
        if result.success:
            _has_pending_changes = False

        if result.success and result.files_uploaded > 0:
            log_for_debugging(
                f"team-memory-watcher: pushed {result.files_uploaded} files",
                level="info",
            )
        elif not result.success:
            log_for_debugging(
                f"team-memory-watcher: push failed: {result.error}", level="warn"
            )
            if is_permanent_failure(result) and _push_suppressed_reason is None:
                _push_suppressed_reason = (
                    f"http_{result.http_status}"
                    if result.http_status is not None
                    else (result.error_type or "unknown")
                )
                log_for_debugging(
                    f"team-memory-watcher: suppressing retry until next unlink or "
                    f"session restart ({_push_suppressed_reason})",
                    level="warn",
                )
                log_event(
                    "tengu_team_mem_push_suppressed",
                    {
                        "reason": _push_suppressed_reason,
                        **(
                            {"status": result.http_status}
                            if result.http_status
                            else {}
                        ),
                    },
                )
    except Exception as e:
        log_for_debugging(
            f"team-memory-watcher: push error: {error_message(e)}", level="warn"
        )
    finally:
        _push_in_progress = False
        _current_push_task = None


def _schedule_push() -> None:
    """
    Debounced push: waits for writes to settle, then pushes once.
    Thread-safe: can be called from watchdog's observer thread.
    """
    global _has_pending_changes, _debounce_task

    if _push_suppressed_reason is not None:
        return

    _has_pending_changes = True

    if _loop is None:
        return

    # Thread-safe: schedule coroutine from possibly a different thread
    asyncio.run_coroutine_threadsafe(_arm_debounce(), _loop)


async def _arm_debounce() -> None:
    """Arm (or re-arm) the debounce timer. Must run on the event loop."""
    global _debounce_task

    if _debounce_task and not _debounce_task.done():
        _debounce_task.cancel()

    _debounce_task = asyncio.create_task(_debounce_and_push())


async def _debounce_and_push() -> None:
    """Wait for the debounce delay, then execute the push."""
    global _debounce_task

    try:
        await asyncio.sleep(DEBOUNCE_S)
    except asyncio.CancelledError:
        return

    global _push_in_progress, _current_push_task

    if _push_in_progress:
        # Re-schedule — push still running; re-arm after it finishes
        _schedule_push()
        return

    _current_push_task = asyncio.create_task(_execute_push())


# ─── Watchdog handler ────────────────────────────────────────


if _WATCHDOG_AVAILABLE:

    class _TeamMemEventHandler(FileSystemEventHandler):
        """
        Handle filesystem events from watchdog.

        Mirrors the behavior of fs.watch in the TypeScript version:
        - Any change fires schedulePush
        - If push is suppressed, stat the changed path to check for unlink
          (ENOENT → file gone → clear suppression)
        """

        def __init__(self, team_dir: str) -> None:
            super().__init__()
            self._team_dir = team_dir

        def on_any_event(self, event: FileSystemEvent) -> None:  # type: ignore[override]
            if event.is_directory:
                return

            global _push_suppressed_reason

            src_path: str = getattr(event, "src_path", "")

            if _push_suppressed_reason is not None:
                # Suppression cleared only by unlink (recovery for too-many-entries)
                if src_path:
                    try:
                        os.stat(src_path)
                        # File still exists — stay suppressed
                    except OSError as e:
                        if e.errno == 2:  # ENOENT
                            if _push_suppressed_reason is not None:
                                log_for_debugging(
                                    f"team-memory-watcher: unlink cleared suppression "
                                    f"(was: {_push_suppressed_reason})",
                                    level="info",
                                )
                                _push_suppressed_reason = None
                                _schedule_push()
                return

            _schedule_push()


async def _start_file_watcher(team_dir: str) -> None:
    """
    Start watching the team memory directory for changes.

    Prefers watchdog (cross-platform, efficient) with its Observer.
    Falls back to an asyncio polling loop if watchdog is not installed.

    The directory is created if it doesn't exist (idempotent mkdir).
    """
    global _watcher_started, _observer, _loop

    if _watcher_started:
        return
    _watcher_started = True

    _loop = asyncio.get_event_loop()

    try:
        await asyncio.to_thread(lambda: os.makedirs(team_dir, exist_ok=True))
    except OSError as e:
        log_for_debugging(
            f"team-memory-watcher: mkdir failed: {error_message(e)}", level="warn"
        )

    if _WATCHDOG_AVAILABLE:
        try:
            observer = Observer()
            handler = _TeamMemEventHandler(team_dir)
            observer.schedule(handler, team_dir, recursive=True)
            observer.start()
            _observer = observer
            log_for_debugging(
                f"team-memory-watcher: watching {team_dir} (watchdog)",
                level="debug",
            )
        except Exception as e:
            log_for_debugging(
                f"team-memory-watcher: failed to start watchdog observer: {error_message(e)}",
                level="warn",
            )
    else:
        # Fallback: asyncio polling loop using os.stat mtime
        asyncio.create_task(_poll_loop(team_dir))
        log_for_debugging(
            f"team-memory-watcher: watching {team_dir} (asyncio poll fallback)",
            level="debug",
        )

    register_cleanup(stop_team_memory_watcher)


async def _poll_loop(team_dir: str, interval_s: float = 1.0) -> None:
    """
    Asyncio-based polling fallback for when watchdog is unavailable.
    Tracks mtime/size of all files under team_dir; fires _schedule_push on change.
    """
    snapshot: dict[str, tuple[float, int]] = {}

    def _snapshot_dir(d: str) -> dict[str, tuple[float, int]]:
        result: dict[str, tuple[float, int]] = {}
        try:
            for dirpath, _dirnames, filenames in os.walk(d):
                for fname in filenames:
                    fpath = os.path.join(dirpath, fname)
                    try:
                        st = os.stat(fpath)
                        result[fpath] = (st.st_mtime, st.st_size)
                    except OSError:
                        pass
        except OSError:
            pass
        return result

    snapshot = await asyncio.to_thread(_snapshot_dir, team_dir)

    while True:
        await asyncio.sleep(interval_s)
        new_snapshot = await asyncio.to_thread(_snapshot_dir, team_dir)

        changed = False
        # Check for modifications or new files
        for path, (mtime, size) in new_snapshot.items():
            old = snapshot.get(path)
            if old is None or old != (mtime, size):
                changed = True
                break

        # Check for deletions
        if not changed:
            for path in snapshot:
                if path not in new_snapshot:
                    # File deleted — clear suppression if needed
                    global _push_suppressed_reason
                    if _push_suppressed_reason is not None:
                        log_for_debugging(
                            f"team-memory-watcher: unlink cleared suppression "
                            f"(was: {_push_suppressed_reason})",
                            level="info",
                        )
                        _push_suppressed_reason = None
                    changed = True
                    break

        snapshot = new_snapshot
        if changed:
            _schedule_push()


# ─── Public API ──────────────────────────────────────────────


async def start_team_memory_watcher() -> None:
    """
    Start the team memory sync system.

    Returns early (before creating any state) if:
      - TEAMMEM feature flag is off
      - team memory is disabled (is_team_memory_enabled)
      - OAuth is not available (is_team_memory_sync_available)
      - the current repo has no github.com remote

    Pulls from server, then starts the file watcher unconditionally.
    The watcher must start even when the server has no content yet
    (fresh repo) — otherwise Claude's first team-memory write depends
    entirely on PostToolUse hooks firing notify_team_memory_write, which
    can miss events on bootstrap.
    """
    global _sync_state

    if not _FEATURE_TEAMMEM:
        return
    if not is_team_memory_enabled() or not is_team_memory_sync_available():
        return

    repo_slug = await get_github_repo()
    if not repo_slug:
        log_for_debugging(
            "team-memory-watcher: no github.com remote, skipping sync",
            level="debug",
        )
        return

    _sync_state = create_sync_state()

    # Initial pull from server (runs before the watcher starts, so its disk
    # writes won't trigger schedule_push)
    initial_pull_success = False
    initial_files_pulled = 0
    server_has_content = False
    try:
        pull_result = await pull_team_memory(_sync_state)
        initial_pull_success = pull_result["success"]
        server_has_content = pull_result.get("entry_count", 0) > 0
        if pull_result["success"] and pull_result.get("files_written", 0) > 0:
            initial_files_pulled = pull_result["files_written"]
            log_for_debugging(
                f"team-memory-watcher: initial pull got {pull_result['files_written']} files",
                level="info",
            )
    except Exception as e:
        log_for_debugging(
            f"team-memory-watcher: initial pull failed: {error_message(e)}",
            level="warn",
        )

    # Always start the watcher. Watching an empty dir is cheap.
    await _start_file_watcher(get_team_mem_path())

    log_event(
        "tengu_team_mem_sync_started",
        {
            "initial_pull_success": initial_pull_success,
            "initial_files_pulled": initial_files_pulled,
            "watcher_started": True,
            "server_has_content": server_has_content,
        },
    )


async def notify_team_memory_write() -> None:
    """
    Call this when a team memory file is written (e.g. from PostToolUse hooks).
    Schedules a push explicitly in case the watcher misses the write —
    a file written in the same tick the watcher starts may not fire an event.
    If the watcher does fire, the debounce timer just resets.
    """
    if not _sync_state:
        return
    _schedule_push()


async def stop_team_memory_watcher() -> None:
    """
    Stop the file watcher and flush pending changes.
    Note: runs within the 2s graceful shutdown budget, so the flush
    is best-effort — if the HTTP PUT doesn't complete in time,
    the process may exit before it finishes.
    """
    global _observer, _debounce_task, _current_push_task

    if _debounce_task and not _debounce_task.done():
        _debounce_task.cancel()
        _debounce_task = None

    if _observer is not None:
        try:
            _observer.stop()  # type: ignore[attr-defined]
            _observer.join()  # type: ignore[attr-defined]
        except Exception:
            pass
        _observer = None

    # Await any in-flight push
    if _current_push_task and not _current_push_task.done():
        try:
            await _current_push_task
        except Exception:
            pass

    # Flush pending changes that were debounced but not yet pushed
    if _has_pending_changes and _sync_state and _push_suppressed_reason is None:
        try:
            await push_team_memory(_sync_state)
        except Exception:
            pass  # Best-effort — shutdown may kill this


# ─── Test helpers ────────────────────────────────────────────


def _reset_watcher_state_for_testing(
    sync_state: Optional[SyncState] = None,
    skip_watcher: bool = False,
    push_suppressed_reason: Optional[str] = None,
) -> None:
    """
    Test-only: reset module state and optionally seed sync_state.
    `skip_watcher=True` marks the watcher as already-started without actually
    starting it. Tests that only exercise the schedule_push/flush path don't
    need a real watcher.
    """
    global _observer, _debounce_task, _push_in_progress, _has_pending_changes
    global _current_push_task, _watcher_started, _push_suppressed_reason, _sync_state

    _observer = None
    _debounce_task = None
    _push_in_progress = False
    _has_pending_changes = False
    _current_push_task = None
    _watcher_started = skip_watcher
    _push_suppressed_reason = push_suppressed_reason
    _sync_state = sync_state


async def _start_file_watcher_for_testing(directory: str) -> None:
    """
    Test-only: start the real watcher on a specified directory.
    Used by fd-count regression tests — start_team_memory_watcher() is
    gated by TEAMMEM feature flag which may be off in tests.
    """
    await _start_file_watcher(directory)
