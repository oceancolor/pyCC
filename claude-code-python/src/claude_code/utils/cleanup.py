"""Cleanup utilities for old session files, message logs, caches, and temp dirs.

Ported from utils/cleanup.ts
"""
from __future__ import annotations

import asyncio
import atexit
import os
import shutil
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

# ---------------------------------------------------------------------------
# Cleanup registry (from utils/cleanupRegistry.ts)
# ---------------------------------------------------------------------------

_handlers: List[Callable[[], None]] = []
_registered = False


def _run_handlers() -> None:
    for h in reversed(_handlers):
        try:
            h()
        except Exception:
            pass


def _setup_signals() -> None:
    global _registered
    if _registered:
        return
    _registered = True
    atexit.register(_run_handlers)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda s, f: (_run_handlers(), sys.exit(0)))
        except (OSError, ValueError):
            pass


def register_cleanup(fn: Callable[[], None]) -> None:
    """Register a function to run on process exit."""
    _setup_signals()
    _handlers.append(fn)


def unregister_cleanup(fn: Callable[[], None]) -> None:
    """Remove a previously registered cleanup function."""
    try:
        _handlers.remove(fn)
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

DEFAULT_CLEANUP_PERIOD_DAYS = 30
ONE_DAY_S = 24 * 60 * 60


def _get_settings():
    """Load settings dict, swallowing import/runtime errors."""
    try:
        from claude_code.utils.settings import get_settings_deprecated  # type: ignore
        return get_settings_deprecated() or {}
    except (ImportError, Exception):
        return {}


def _get_settings_with_all_errors():
    """Return (settings, errors) tuple."""
    try:
        from claude_code.utils.settings import get_settings_with_all_errors  # type: ignore
        return get_settings_with_all_errors()
    except (ImportError, Exception):
        return {}, []


def _raw_settings_contains_key(key: str) -> bool:
    try:
        from claude_code.utils.settings import raw_settings_contains_key  # type: ignore
        return raw_settings_contains_key(key)
    except (ImportError, Exception):
        return False


def _get_cutoff_date() -> datetime:
    settings = _get_settings()
    cleanup_period_days = settings.get("cleanupPeriodDays", DEFAULT_CLEANUP_PERIOD_DAYS)
    try:
        cleanup_period_days = int(cleanup_period_days)
    except (TypeError, ValueError):
        cleanup_period_days = DEFAULT_CLEANUP_PERIOD_DAYS
    cutoff_ts = datetime.now(tz=timezone.utc).timestamp() - cleanup_period_days * 24 * 60 * 60
    return datetime.fromtimestamp(cutoff_ts, tz=timezone.utc)


def _get_claude_config_home_dir() -> str:
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir  # type: ignore
        return get_claude_config_home_dir()
    except (ImportError, Exception):
        return os.path.join(os.path.expanduser("~"), ".claude")


def _get_projects_dir() -> str:
    try:
        from claude_code.utils.session_storage import get_projects_dir  # type: ignore
        return get_projects_dir()
    except (ImportError, Exception):
        return os.path.join(_get_claude_config_home_dir(), "projects")


def _get_cache_paths():
    """Return an object-like helper for CACHE_PATHS."""
    try:
        from claude_code.utils.cache_paths import CACHE_PATHS  # type: ignore
        return CACHE_PATHS
    except (ImportError, Exception):
        class _CachePaths:
            @staticmethod
            def errors() -> str:
                return os.path.join(_get_claude_config_home_dir(), "errors")

            @staticmethod
            def base_logs() -> str:
                return os.path.join(_get_claude_config_home_dir(), "logs")
        return _CachePaths()


def _log_error(err: Exception) -> None:
    try:
        from claude_code.utils.log import log_error  # type: ignore
        log_error(err)
    except (ImportError, Exception):
        pass  # swallow


def _log_for_debugging(msg: str) -> None:
    try:
        from claude_code.utils.debug import log_for_debugging  # type: ignore
        log_for_debugging(msg)
    except (ImportError, Exception):
        pass


def _log_event(name: str, data: dict) -> None:
    try:
        from claude_code.services.analytics import log_event  # type: ignore
        log_event(name, data)
    except (ImportError, Exception):
        pass


TOOL_RESULTS_SUBDIR = "tool-results"


# ---------------------------------------------------------------------------
# CleanupResult
# ---------------------------------------------------------------------------

@dataclass
class CleanupResult:
    """Result of a cleanup operation."""
    messages: int = 0
    errors: int = 0


def add_cleanup_results(a: CleanupResult, b: CleanupResult) -> CleanupResult:
    """Merge two CleanupResult objects."""
    return CleanupResult(messages=a.messages + b.messages, errors=a.errors + b.errors)


# ---------------------------------------------------------------------------
# Filename <-> date conversion
# ---------------------------------------------------------------------------

def convert_file_name_to_date(filename: str) -> datetime:
    """Convert a log filename (with '-' instead of ':') back to a datetime.

    Files are named like ``2024-01-15T14-30-00-000Z.jsonl``.
    """
    base = filename.split(".")[0]
    # Replace time separator pattern T14-30-00-000Z → T14:30:00.000Z
    import re
    iso_str = re.sub(r"T(\d{2})-(\d{2})-(\d{2})-(\d{3})Z", r"T\1:\2:\3.\4Z", base)
    try:
        # Python 3.11+: datetime.fromisoformat handles Z
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        return datetime.fromisoformat(iso_str)
    except ValueError:
        # Fallback: epoch
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Low-level filesystem helpers
# ---------------------------------------------------------------------------

async def _try_rmdir(dir_path: str) -> None:
    """Remove directory if empty; silently ignore failures."""
    try:
        os.rmdir(dir_path)
    except OSError:
        pass


async def _unlink_if_old(file_path: str, cutoff_date: datetime) -> bool:
    """Delete *file_path* if its mtime is older than *cutoff_date*.

    Returns True if the file was deleted.
    """
    try:
        stat = os.stat(file_path)
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        if mtime < cutoff_date:
            os.unlink(file_path)
            return True
    except OSError:
        pass
    return False


# ---------------------------------------------------------------------------
# Cleanup of old log files in a directory
# ---------------------------------------------------------------------------

async def _cleanup_old_files_in_directory(
    dir_path: str,
    cutoff_date: datetime,
    is_message_path: bool,
) -> CleanupResult:
    """Delete files in *dir_path* whose names parse to a timestamp older than *cutoff_date*."""
    result = CleanupResult()
    try:
        entries = os.scandir(dir_path)
    except FileNotFoundError:
        return result
    except OSError as exc:
        _log_error(exc)
        return result

    with entries as scan:
        for entry in scan:
            if not entry.is_file():
                continue
            try:
                timestamp = convert_file_name_to_date(entry.name)
                if timestamp < cutoff_date:
                    os.unlink(entry.path)
                    if is_message_path:
                        result.messages += 1
                    else:
                        result.errors += 1
            except Exception as exc:
                _log_error(exc)

    return result


async def cleanup_old_message_files() -> CleanupResult:
    """Clean up old error and MCP log files."""
    cutoff_date = _get_cutoff_date()
    cache_paths = _get_cache_paths()

    error_path = cache_paths.errors()
    base_cache_path = cache_paths.base_logs()

    result = await _cleanup_old_files_in_directory(error_path, cutoff_date, False)

    try:
        try:
            entries = list(os.scandir(base_cache_path))
        except OSError:
            return result

        mcp_log_dirs = [
            entry.path
            for entry in entries
            if entry.is_dir() and entry.name.startswith("mcp-logs-")
        ]

        for mcp_log_dir in mcp_log_dirs:
            sub = await _cleanup_old_files_in_directory(mcp_log_dir, cutoff_date, True)
            result = add_cleanup_results(result, sub)
            await _try_rmdir(mcp_log_dir)
    except OSError as exc:
        if getattr(exc, "errno", None) != 2:  # ENOENT
            _log_error(exc)

    return result


# ---------------------------------------------------------------------------
# Cleanup of old session files
# ---------------------------------------------------------------------------

async def cleanup_old_session_files() -> CleanupResult:
    """Remove old .jsonl/.cast session files and empty tool-result dirs."""
    cutoff_date = _get_cutoff_date()
    result = CleanupResult()
    projects_dir = _get_projects_dir()

    try:
        project_entries = list(os.scandir(projects_dir))
    except OSError:
        return result

    for project_dirent in project_entries:
        if not project_dirent.is_dir():
            continue
        project_dir = project_dirent.path

        try:
            entries = list(os.scandir(project_dir))
        except OSError:
            result.errors += 1
            continue

        for entry in entries:
            if entry.is_file():
                if not (entry.name.endswith(".jsonl") or entry.name.endswith(".cast")):
                    continue
                try:
                    deleted = await _unlink_if_old(entry.path, cutoff_date)
                    if deleted:
                        result.messages += 1
                except OSError:
                    result.errors += 1

            elif entry.is_dir():
                session_dir = entry.path
                tool_results_dir = os.path.join(session_dir, TOOL_RESULTS_SUBDIR)

                try:
                    tool_dirs = list(os.scandir(tool_results_dir))
                except OSError:
                    await _try_rmdir(session_dir)
                    continue

                for tool_entry in tool_dirs:
                    if tool_entry.is_file():
                        try:
                            deleted = await _unlink_if_old(tool_entry.path, cutoff_date)
                            if deleted:
                                result.messages += 1
                        except OSError:
                            result.errors += 1
                    elif tool_entry.is_dir():
                        tool_dir_path = tool_entry.path
                        try:
                            tool_files = list(os.scandir(tool_dir_path))
                        except OSError:
                            continue
                        for tf in tool_files:
                            if not tf.is_file():
                                continue
                            try:
                                deleted = await _unlink_if_old(tf.path, cutoff_date)
                                if deleted:
                                    result.messages += 1
                            except OSError:
                                result.errors += 1
                        await _try_rmdir(tool_dir_path)

                await _try_rmdir(tool_results_dir)
                await _try_rmdir(session_dir)

        await _try_rmdir(project_dir)

    return result


# ---------------------------------------------------------------------------
# Generic single-directory cleanup
# ---------------------------------------------------------------------------

async def _cleanup_single_directory(
    dir_path: str,
    extension: str,
    remove_empty_dir: bool = True,
) -> CleanupResult:
    """Delete files with *extension* in *dir_path* that are older than cutoff."""
    cutoff_date = _get_cutoff_date()
    result = CleanupResult()

    try:
        dirents = list(os.scandir(dir_path))
    except OSError:
        return result

    for dirent in dirents:
        if not dirent.is_file() or not dirent.name.endswith(extension):
            continue
        try:
            deleted = await _unlink_if_old(dirent.path, cutoff_date)
            if deleted:
                result.messages += 1
        except OSError:
            result.errors += 1

    if remove_empty_dir:
        await _try_rmdir(dir_path)

    return result


async def cleanup_old_plan_files() -> CleanupResult:
    """Remove old plan .md files from ~/.claude/plans/."""
    plans_dir = os.path.join(_get_claude_config_home_dir(), "plans")
    return await _cleanup_single_directory(plans_dir, ".md")


# ---------------------------------------------------------------------------
# File-history backups
# ---------------------------------------------------------------------------

async def cleanup_old_file_history_backups() -> CleanupResult:
    """Remove old file-history session directories."""
    cutoff_date = _get_cutoff_date()
    result = CleanupResult()

    config_dir = _get_claude_config_home_dir()
    file_history_storage_dir = os.path.join(config_dir, "file-history")

    try:
        dirents = list(os.scandir(file_history_storage_dir))
    except OSError:
        return result

    session_dirs = [d.path for d in dirents if d.is_dir()]

    async def _remove_session(session_dir: str) -> None:
        try:
            stat = os.stat(session_dir)
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if mtime < cutoff_date:
                shutil.rmtree(session_dir, ignore_errors=True)
                result.messages += 1
        except OSError:
            result.errors += 1

    await asyncio.gather(*[_remove_session(d) for d in session_dirs])
    await _try_rmdir(file_history_storage_dir)
    return result


# ---------------------------------------------------------------------------
# Session-env dirs
# ---------------------------------------------------------------------------

async def cleanup_old_session_env_dirs() -> CleanupResult:
    """Remove old session-env directories from ~/.claude/session-env/."""
    cutoff_date = _get_cutoff_date()
    result = CleanupResult()

    config_dir = _get_claude_config_home_dir()
    session_env_base_dir = os.path.join(config_dir, "session-env")

    try:
        dirents = list(os.scandir(session_env_base_dir))
    except OSError:
        return result

    for dirent in dirents:
        if not dirent.is_dir():
            continue
        try:
            stat = os.stat(dirent.path)
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if mtime < cutoff_date:
                shutil.rmtree(dirent.path, ignore_errors=True)
                result.messages += 1
        except OSError:
            result.errors += 1

    await _try_rmdir(session_env_base_dir)
    return result


# ---------------------------------------------------------------------------
# Debug logs
# ---------------------------------------------------------------------------

async def cleanup_old_debug_logs() -> CleanupResult:
    """Remove old .txt debug log files, preserving the 'latest' symlink."""
    cutoff_date = _get_cutoff_date()
    result = CleanupResult()

    debug_dir = os.path.join(_get_claude_config_home_dir(), "debug")

    try:
        dirents = list(os.scandir(debug_dir))
    except OSError:
        return result

    for dirent in dirents:
        if not dirent.is_file():
            continue
        if not dirent.name.endswith(".txt") or dirent.name == "latest":
            continue
        try:
            deleted = await _unlink_if_old(dirent.path, cutoff_date)
            if deleted:
                result.messages += 1
        except OSError:
            result.errors += 1

    # Intentionally do NOT remove debugDir — needed for future logs
    return result


# ---------------------------------------------------------------------------
# Image caches
# ---------------------------------------------------------------------------

async def _cleanup_old_image_caches() -> CleanupResult:
    """Delegate to imageStore helper if available."""
    try:
        from claude_code.utils.image_store import cleanup_old_image_caches  # type: ignore
        return await cleanup_old_image_caches()
    except (ImportError, Exception):
        return CleanupResult()


# ---------------------------------------------------------------------------
# Paste store
# ---------------------------------------------------------------------------

async def _cleanup_old_pastes() -> CleanupResult:
    """Delegate to pasteStore helper if available."""
    try:
        from claude_code.utils.paste_store import cleanup_old_pastes  # type: ignore
        cutoff_date = _get_cutoff_date()
        return await cleanup_old_pastes(cutoff_date)
    except (ImportError, Exception):
        return CleanupResult()


# ---------------------------------------------------------------------------
# Agent worktrees
# ---------------------------------------------------------------------------

async def _cleanup_stale_agent_worktrees() -> int:
    """Return count of removed worktrees; 0 on any error."""
    try:
        from claude_code.utils.worktree import cleanup_stale_agent_worktrees  # type: ignore
        cutoff_date = _get_cutoff_date()
        return await cleanup_stale_agent_worktrees(cutoff_date)
    except (ImportError, Exception):
        return 0


# ---------------------------------------------------------------------------
# Old native-installer versions
# ---------------------------------------------------------------------------

async def _cleanup_old_versions() -> None:
    try:
        from claude_code.utils.native_installer import cleanup_old_versions  # type: ignore
        await cleanup_old_versions()
    except (ImportError, Exception):
        pass


# ---------------------------------------------------------------------------
# npm cache cleanup (Anthropic internal; skipped in OSS builds)
# ---------------------------------------------------------------------------

async def cleanup_npm_cache_for_anthropic_packages() -> None:
    """Thin stub — npm-specific logic not applicable in Python builds."""
    _log_for_debugging("npm cache cleanup: skipped (Python build)")


# ---------------------------------------------------------------------------
# Throttled old-versions cleanup
# ---------------------------------------------------------------------------

async def cleanup_old_versions_throttled() -> None:
    """Run cleanupOldVersions at most once per day using a marker file."""
    import time

    marker_path = os.path.join(_get_claude_config_home_dir(), ".version-cleanup")

    # Check if we ran recently
    try:
        stat = os.stat(marker_path)
        if time.time() - stat.st_mtime < ONE_DAY_S:
            _log_for_debugging("version cleanup: skipping, ran recently")
            return
    except FileNotFoundError:
        pass
    except OSError:
        pass

    # Simple file-lock: create exclusively; skip if another process has it
    lock_path = marker_path + ".lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        _log_for_debugging("version cleanup: skipping, lock held")
        return
    except OSError:
        return

    _log_for_debugging("version cleanup: starting (throttled)")

    try:
        await _cleanup_old_versions()
        Path(marker_path).write_text(datetime.now(tz=timezone.utc).isoformat())
    except Exception as exc:
        _log_error(exc)
    finally:
        try:
            os.unlink(lock_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def cleanup_old_message_files_in_background() -> None:
    """Run all cleanup tasks.  Skip if settings have errors and cleanupPeriodDays is set."""
    _settings, errors = _get_settings_with_all_errors()
    if errors and _raw_settings_contains_key("cleanupPeriodDays"):
        _log_for_debugging(
            "Skipping cleanup: settings have validation errors but cleanupPeriodDays was "
            "explicitly set. Fix settings errors to enable cleanup."
        )
        return

    await cleanup_old_message_files()
    await cleanup_old_session_files()
    await cleanup_old_plan_files()
    await cleanup_old_file_history_backups()
    await cleanup_old_session_env_dirs()
    await cleanup_old_debug_logs()
    await _cleanup_old_image_caches()
    await _cleanup_old_pastes()

    removed_worktrees = await _cleanup_stale_agent_worktrees()
    if removed_worktrees > 0:
        _log_event("tengu_worktree_cleanup", {"removed": removed_worktrees})

    user_type = os.environ.get("USER_TYPE", "")
    if user_type == "ant":
        await cleanup_npm_cache_for_anthropic_packages()


# ---------------------------------------------------------------------------
# Convenience sync entry-point (wraps asyncio.run)
# ---------------------------------------------------------------------------

def run_cleanup_sync() -> None:
    """Synchronous wrapper around :func:`cleanup_old_message_files_in_background`."""
    asyncio.run(cleanup_old_message_files_in_background())
