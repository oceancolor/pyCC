"""
team_memory_sync/watcher.py — Team Memory File Watcher.
Ported from services/teamMemorySync/watcher.ts (387 lines).

Watches the team memory directory for changes and triggers
a debounced push to the server when files are modified.
Performs an initial pull on startup, then starts a directory-level
watchdog observer so first-time writes to a fresh repo get picked up.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEBOUNCE_S = 2.0  # Wait 2 seconds after last change before pushing

# ─── Watcher state ──────────────────────────────────────────────────────────

_watcher_observer = None           # watchdog Observer instance
_debounce_task: Optional[asyncio.Task] = None
_push_in_progress: bool = False
_has_pending_changes: bool = False
_current_push_task: Optional[asyncio.Task] = None
_watcher_started: bool = False
_push_suppressed_reason: Optional[str] = None
_sync_state = None                 # SyncState | None


# ---------------------------------------------------------------------------
# isPermanentFailure
# ---------------------------------------------------------------------------

def is_permanent_failure(result) -> bool:
    """
    Permanent = retry without user action will fail the same way.
    - no_oauth / no_repo: pre-request client checks, no status code
    - 4xx except 409/429: client error (404 missing repo, 413 too many
      entries, 403 permission). 409 is a transient conflict. 429 is rate limit.
    """
    error_type = getattr(result, "error_type", None)
    if error_type in ("no_oauth", "no_repo"):
        return True
    http_status = getattr(result, "http_status", None)
    if (
        http_status is not None
        and 400 <= http_status < 500
        and http_status != 409
        and http_status != 429
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Push execution
# ---------------------------------------------------------------------------

async def _execute_push() -> None:
    """Execute the push and track its lifecycle."""
    global _push_in_progress, _has_pending_changes, _current_push_task, _push_suppressed_reason

    if _sync_state is None:
        return

    _push_in_progress = True
    try:
        from claude_code.services.team_memory_sync.index import push_team_memory
        result = await push_team_memory(_sync_state)

        if result.success:
            _has_pending_changes = False

        if result.success and result.files_uploaded > 0:
            logger.info("team-memory-watcher: pushed %d files", result.files_uploaded)
        elif not result.success:
            logger.warning("team-memory-watcher: push failed: %s", result.error)
            if is_permanent_failure(result) and _push_suppressed_reason is None:
                http_status = getattr(result, "http_status", None)
                error_type = getattr(result, "error_type", None)
                if http_status is not None:
                    _push_suppressed_reason = f"http_{http_status}"
                else:
                    _push_suppressed_reason = error_type or "unknown"
                logger.warning(
                    "team-memory-watcher: suppressing retry (reason=%s)",
                    _push_suppressed_reason,
                )
                try:
                    from claude_code.services.analytics import log_event
                    log_event("tengu_team_mem_push_suppressed", {
                        "reason": _push_suppressed_reason,
                        **({"status": http_status} if http_status else {}),
                    })
                except (ImportError, Exception):
                    pass
    except Exception as e:
        logger.warning("team-memory-watcher: push error: %s", e)
    finally:
        _push_in_progress = False
        _current_push_task = None


# ---------------------------------------------------------------------------
# Debounced push scheduler
# ---------------------------------------------------------------------------

async def _debounced_push() -> None:
    """Sleep DEBOUNCE_S then run push (re-schedules if push is in progress)."""
    await asyncio.sleep(DEBOUNCE_S)
    if _push_in_progress:
        # Re-schedule
        _schedule_push()
        return
    await _execute_push()


def _schedule_push() -> None:
    """Debounced push: waits for writes to settle, then pushes once."""
    global _debounce_task, _has_pending_changes

    if _push_suppressed_reason is not None:
        return

    _has_pending_changes = True

    if _debounce_task is not None and not _debounce_task.done():
        _debounce_task.cancel()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _debounce_task = loop.create_task(_debounced_push())
    except RuntimeError:
        # No running event loop — fire-and-forget from sync context
        asyncio.run(_execute_push())


# ---------------------------------------------------------------------------
# File watcher event handler
# ---------------------------------------------------------------------------

def _make_watchdog_handler(team_dir: str):
    """Create a watchdog event handler for the team memory directory."""
    try:
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        return None

    watcher_ref = {"push_suppressed_reason": _push_suppressed_reason}

    class TeamMemHandler(FileSystemEventHandler):
        def on_any_event(self, event):
            global _push_suppressed_reason

            if _push_suppressed_reason is not None:
                # Suppression is only cleared by unlink (recovery action for
                # too-many-entries). stat the file to disambiguate.
                filename = getattr(event, "src_path", None)
                if filename and not os.path.exists(filename):
                    if _push_suppressed_reason is not None:
                        logger.info(
                            "team-memory-watcher: unlink cleared suppression (was: %s)",
                            _push_suppressed_reason,
                        )
                        _push_suppressed_reason = None
                    _schedule_push()
                return

            _schedule_push()

    return TeamMemHandler()


# ---------------------------------------------------------------------------
# Start file watcher
# ---------------------------------------------------------------------------

async def _start_file_watcher(team_dir: str) -> None:
    """
    Start watching the team memory directory for changes.

    Uses watchdog for cross-platform file system watching.
    Mirrors the fs.watch({recursive: true}) approach from the TS version.
    """
    global _watcher_observer, _watcher_started

    if _watcher_started:
        return
    _watcher_started = True

    try:
        os.makedirs(team_dir, exist_ok=True)

        try:
            from watchdog.observers import Observer

            handler = _make_watchdog_handler(team_dir)
            if handler is None:
                logger.warning("team-memory-watcher: watchdog not available, skipping watch")
                return

            _watcher_observer = Observer()
            _watcher_observer.schedule(handler, team_dir, recursive=True)
            _watcher_observer.start()
            logger.debug("team-memory-watcher: watching %s", team_dir)

        except ImportError:
            logger.warning(
                "team-memory-watcher: watchdog not installed, file watching disabled. "
                "Install with: pip install watchdog"
            )
        except Exception as err:
            logger.warning("team-memory-watcher: failed to watch %s: %s", team_dir, err)

        # Register cleanup
        try:
            from claude_code.utils.cleanup_registry import register_cleanup
            register_cleanup(stop_team_memory_watcher)
        except (ImportError, Exception):
            pass

    except Exception as err:
        logger.warning("team-memory-watcher: failed to start watcher: %s", err)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def start_team_memory_watcher() -> None:
    """
    Start the team memory sync system.

    Returns early (before creating any state) if:
    - TEAMMEM build flag is off
    - team memory is disabled (is_team_memory_enabled)
    - OAuth is not available (is_team_memory_sync_available)
    - the current repo has no github.com remote
    """
    global _sync_state

    # Check TEAMMEM feature gate
    try:
        from claude_code.utils.feature_flags import is_feature_enabled
        if not is_feature_enabled("TEAMMEM"):
            return
    except (ImportError, Exception):
        return

    try:
        from claude_code.memdir.team_mem_paths import (
            is_team_memory_enabled,
            get_team_mem_path,
        )
        from claude_code.services.team_memory_sync.index import (
            is_team_memory_sync_available,
            create_sync_state,
            pull_team_memory,
            push_team_memory,
        )
    except ImportError:
        return

    if not is_team_memory_enabled():
        return
    if not is_team_memory_sync_available():
        return

    # Check for github.com remote
    try:
        from claude_code.utils.git import get_github_repo
        repo_slug = await get_github_repo()
    except (ImportError, Exception):
        repo_slug = None

    if not repo_slug:
        logger.debug("team-memory-watcher: no github.com remote, skipping sync")
        return

    _sync_state = create_sync_state()

    # Initial pull from server
    initial_pull_success = False
    initial_files_pulled = 0
    server_has_content = False
    try:
        pull_result = await pull_team_memory(_sync_state)
        initial_pull_success = pull_result.success
        server_has_content = pull_result.entry_count > 0
        if pull_result.success and pull_result.files_written > 0:
            initial_files_pulled = pull_result.files_written
            logger.info(
                "team-memory-watcher: initial pull got %d files",
                pull_result.files_written,
            )
    except Exception as e:
        logger.warning("team-memory-watcher: initial pull failed: %s", e)

    # Always start the watcher (even for empty/fresh repos)
    team_dir = get_team_mem_path()
    await _start_file_watcher(team_dir)

    # Log event
    try:
        from claude_code.services.analytics import log_event
        log_event("tengu_team_mem_sync_started", {
            "initial_pull_success": initial_pull_success,
            "initial_files_pulled": initial_files_pulled,
            "watcher_started": True,
            "server_has_content": server_has_content,
        })
    except (ImportError, Exception):
        pass


async def notify_team_memory_write() -> None:
    """
    Call this when a team memory file is written (e.g. from PostToolUse hooks).
    Schedules a push explicitly in case the file watcher misses the write.
    """
    if _sync_state is None:
        return
    _schedule_push()


async def stop_team_memory_watcher() -> None:
    """
    Stop the file watcher and flush pending changes.
    Runs within the graceful shutdown budget, so the flush is best-effort.
    """
    global _debounce_task, _watcher_observer, _has_pending_changes, _current_push_task

    if _debounce_task is not None and not _debounce_task.done():
        _debounce_task.cancel()
        _debounce_task = None

    if _watcher_observer is not None:
        try:
            _watcher_observer.stop()
            _watcher_observer.join(timeout=2.0)
        except Exception:
            pass
        _watcher_observer = None

    # Await any in-flight push
    if _current_push_task is not None:
        try:
            await _current_push_task
        except Exception:
            pass

    # Flush pending changes that were debounced but not yet pushed
    if _has_pending_changes and _sync_state is not None and _push_suppressed_reason is None:
        try:
            from claude_code.services.team_memory_sync.index import push_team_memory
            await push_team_memory(_sync_state)
        except Exception:
            pass  # Best-effort — shutdown may kill this


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _reset_watcher_state_for_testing(
    sync_state=None,
    skip_watcher: bool = False,
    push_suppressed_reason=None,
) -> None:
    """
    Test-only: reset module state and optionally seed sync_state.
    `skip_watcher=True` marks the watcher as already-started without starting it.
    """
    global _watcher_observer, _debounce_task, _push_in_progress
    global _has_pending_changes, _current_push_task, _watcher_started
    global _push_suppressed_reason, _sync_state
    _watcher_observer = None
    _debounce_task = None
    _push_in_progress = False
    _has_pending_changes = False
    _current_push_task = None
    _watcher_started = skip_watcher
    _push_suppressed_reason = push_suppressed_reason
    _sync_state = sync_state


async def _start_file_watcher_for_testing(directory: str) -> None:
    """
    Test-only: start the real file watcher on a specified directory.
    Used by fd-count regression tests.
    """
    await _start_file_watcher(directory)
