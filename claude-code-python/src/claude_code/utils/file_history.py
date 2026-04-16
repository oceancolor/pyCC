"""
File edit history (undo/checkpoint support).
Python port of utils/fileHistory.ts

Stores file backups in ~/.claude/file-history/<session_id>/<hash>@v<n>
Tracks snapshots per message ID, supports rewind (restore to prior snapshot).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat as stat_mod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, Any

# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

# backupFileName: str = backup file name, None = file did not exist at this version
BackupFileName = Optional[str]


@dataclass
class FileHistoryBackup:
    backup_file_name: BackupFileName  # None means file did not exist
    version: int
    backup_time: datetime


@dataclass
class FileHistorySnapshot:
    message_id: str  # UUID of the associated message
    tracked_file_backups: Dict[str, FileHistoryBackup]  # tracking_path -> backup
    timestamp: datetime


@dataclass
class FileHistoryState:
    snapshots: List[FileHistorySnapshot] = field(default_factory=list)
    tracked_files: Set[str] = field(default_factory=set)
    # Monotonically-increasing counter; incremented on every snapshot even when old
    # ones are evicted. Used as an activity signal.
    snapshot_sequence: int = 0


@dataclass
class DiffStats:
    insertions: int = 0
    deletions: int = 0
    files_changed: Optional[List[str]] = None


MAX_SNAPSHOTS = 100

# ---------------------------------------------------------------------------
# Helpers: session / config
# ---------------------------------------------------------------------------

_SESSION_ID: Optional[str] = None
_ORIGINAL_CWD: Optional[str] = None


def _get_session_id() -> str:
    """Return current session ID (set via set_session_id or env var)."""
    global _SESSION_ID
    if _SESSION_ID:
        return _SESSION_ID
    return os.environ.get("CLAUDE_SESSION_ID", "default-session")


def set_session_id(session_id: str) -> None:
    """Override the session ID used for backup paths."""
    global _SESSION_ID
    _SESSION_ID = session_id


def _get_original_cwd() -> str:
    """Return the original working directory."""
    global _ORIGINAL_CWD
    if _ORIGINAL_CWD:
        return _ORIGINAL_CWD
    return os.environ.get("CLAUDE_ORIGINAL_CWD", os.getcwd())


def set_original_cwd(cwd: str) -> None:
    global _ORIGINAL_CWD
    _ORIGINAL_CWD = cwd


def _get_claude_config_home_dir() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
    return base


def _is_env_truthy(value: Optional[str]) -> bool:
    if not value:
        return False
    return value.lower().strip() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Enable check
# ---------------------------------------------------------------------------

def file_history_enabled() -> bool:
    """Return True if file history/checkpointing is enabled."""
    # SDK (non-interactive) session check
    is_non_interactive = _is_env_truthy(os.environ.get("CLAUDE_CODE_NON_INTERACTIVE"))
    if is_non_interactive:
        return (
            _is_env_truthy(os.environ.get("CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING"))
            and not _is_env_truthy(os.environ.get("CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING"))
        )
    # Interactive session
    disable = _is_env_truthy(os.environ.get("CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING"))
    if disable:
        return False
    return True


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

def _get_backup_file_name(file_path: str, version: int) -> str:
    """Compute a deterministic backup file name: <sha256[:16]>@v<version>"""
    hash_hex = hashlib.sha256(file_path.encode()).hexdigest()[:16]
    return f"{hash_hex}@v{version}"


def _resolve_backup_path(backup_file_name: str, session_id: Optional[str] = None) -> Path:
    """Resolve the absolute path of a backup file."""
    config_dir = _get_claude_config_home_dir()
    sid = session_id or _get_session_id()
    return Path(config_dir) / "file-history" / sid / backup_file_name


def _maybe_shorten_file_path(file_path: str) -> str:
    """Use relative path as tracking key if under original cwd."""
    if not os.path.isabs(file_path):
        return file_path
    cwd = _get_original_cwd()
    try:
        rel = os.path.relpath(file_path, cwd)
        # Don't use ".." relative paths
        if not rel.startswith(".."):
            return rel
    except ValueError:
        pass
    return file_path


def _maybe_expand_file_path(file_path: str) -> str:
    """Expand a relative tracking path to an absolute path."""
    if os.path.isabs(file_path):
        return file_path
    return os.path.join(_get_original_cwd(), file_path)


# ---------------------------------------------------------------------------
# Backup I/O
# ---------------------------------------------------------------------------

def _create_backup(file_path: Optional[str], version: int) -> FileHistoryBackup:
    """
    Create a backup of file_path at the given version.
    If file_path is None or file does not exist, records a null backup.
    """
    if file_path is None:
        return FileHistoryBackup(backup_file_name=None, version=version, backup_time=datetime.now())

    backup_file_name = _get_backup_file_name(file_path, version)
    backup_path = _resolve_backup_path(backup_file_name)

    # Stat the source first
    try:
        src_stat = os.stat(file_path)
    except FileNotFoundError:
        return FileHistoryBackup(backup_file_name=None, version=version, backup_time=datetime.now())
    except OSError:
        raise

    # Lazy mkdir: try to copy, create dir on ENOENT
    try:
        shutil.copy2(file_path, str(backup_path))
    except FileNotFoundError:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, str(backup_path))

    # Preserve permissions
    os.chmod(str(backup_path), stat_mod.S_IMODE(src_stat.st_mode))

    return FileHistoryBackup(
        backup_file_name=backup_file_name,
        version=version,
        backup_time=datetime.now(),
    )


def _restore_backup(file_path: str, backup_file_name: str) -> None:
    """Restore a file from its backup."""
    backup_path = _resolve_backup_path(backup_file_name)

    try:
        backup_stat = os.stat(str(backup_path))
    except FileNotFoundError:
        return

    try:
        shutil.copy2(str(backup_path), file_path)
    except FileNotFoundError:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(backup_path), file_path)

    os.chmod(file_path, stat_mod.S_IMODE(backup_stat.st_mode))


def _get_backup_file_name_first_version(
    tracking_path: str, state: FileHistoryState
) -> Optional[BackupFileName]:
    """
    Get the backup file name for version=1 of a tracked file.
    Returns BackupFileName (str|None) if found, or the sentinel _UNDEFINED if not found.
    Returns None (null marker) if file didn't exist at v1.
    Returns a string if file existed at v1.
    Returns _UNDEFINED (represented here as a special sentinel) if we can't find it.
    """
    for snapshot in state.snapshots:
        backup = snapshot.tracked_file_backups.get(tracking_path)
        if backup is not None and backup.version == 1:
            return backup.backup_file_name
    return _UNDEFINED_SENTINEL


_UNDEFINED_SENTINEL = object()  # sentinel for "not found"


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def check_origin_file_changed(
    original_file: str,
    backup_file_name: str,
    original_stats_hint: Optional[os.stat_result] = None,
) -> bool:
    """
    Check if the original file has changed compared to its backup.
    Returns True if changed (or if either file is missing unexpectedly).
    """
    backup_path = str(_resolve_backup_path(backup_file_name))

    # Stat original
    original_stat: Optional[os.stat_result] = original_stats_hint
    if original_stat is None:
        try:
            original_stat = os.stat(original_file)
        except FileNotFoundError:
            original_stat = None
        except OSError:
            return True  # unexpected error -> treat as changed

    # Stat backup
    backup_stat: Optional[os.stat_result] = None
    try:
        backup_stat = os.stat(backup_path)
    except FileNotFoundError:
        backup_stat = None
    except OSError:
        return True

    # One exists, one missing -> changed
    if (original_stat is None) != (backup_stat is None):
        return True
    # Both missing -> no change
    if original_stat is None or backup_stat is None:
        return False

    # Check mode and size
    if (stat_mod.S_IMODE(original_stat.st_mode) != stat_mod.S_IMODE(backup_stat.st_mode)
            or original_stat.st_size != backup_stat.st_size):
        return True

    # If original was modified before backup was created, skip content check
    if original_stat.st_mtime_ns < backup_stat.st_mtime_ns:
        return False

    # Content comparison
    try:
        with open(original_file, "rb") as f:
            orig_content = f.read()
        with open(backup_path, "rb") as f:
            back_content = f.read()
        return orig_content != back_content
    except OSError:
        return True  # file deleted between stat and read -> changed


# ---------------------------------------------------------------------------
# Diff stats
# ---------------------------------------------------------------------------

def _compute_diff_stats_for_file(
    original_file: str, backup_file_name: Optional[str] = None
) -> DiffStats:
    """Compute line-level diff stats between original and backup."""
    try:
        backup_path = str(_resolve_backup_path(backup_file_name)) if backup_file_name else None

        original_content: Optional[str] = None
        backup_content: Optional[str] = None

        try:
            with open(original_file, "r", encoding="utf-8", errors="replace") as f:
                original_content = f.read()
        except FileNotFoundError:
            pass

        if backup_path:
            try:
                with open(backup_path, "r", encoding="utf-8", errors="replace") as f:
                    backup_content = f.read()
            except FileNotFoundError:
                pass

        if original_content is None and backup_content is None:
            return DiffStats(files_changed=[])

        # Simple line-based diff
        orig_lines = (original_content or "").splitlines(keepends=True)
        back_lines = (backup_content or "").splitlines(keepends=True)

        insertions, deletions = _count_line_diff(back_lines, orig_lines)
        return DiffStats(insertions=insertions, deletions=deletions, files_changed=[original_file])

    except Exception:
        return DiffStats(files_changed=[])


def _count_line_diff(
    old_lines: List[str], new_lines: List[str]
) -> Tuple[int, int]:
    """
    Count inserted and deleted lines using a simple LCS-based diff.
    Returns (insertions, deletions) where:
      - insertions = lines added in new vs old
      - deletions  = lines removed in new vs old
    """
    # Use difflib for accuracy
    import difflib
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    insertions = 0
    deletions = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            deletions += i2 - i1
            insertions += j2 - j1
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "insert":
            insertions += j2 - j1
    return insertions, deletions


# ---------------------------------------------------------------------------
# Apply snapshot (rewind)
# ---------------------------------------------------------------------------

def _apply_snapshot(
    state: FileHistoryState, target_snapshot: FileHistorySnapshot
) -> List[str]:
    """Apply the given snapshot's file state to disk. Returns list of changed paths."""
    files_changed: List[str] = []

    for tracking_path in state.tracked_files:
        file_path = _maybe_expand_file_path(tracking_path)
        target_backup = target_snapshot.tracked_file_backups.get(tracking_path)

        if target_backup is not None:
            backup_file_name: Any = target_backup.backup_file_name
        else:
            bfn = _get_backup_file_name_first_version(tracking_path, state)
            if bfn is _UNDEFINED_SENTINEL:
                # Can't find first version — skip
                continue
            backup_file_name = bfn  # str or None

        if backup_file_name is None:
            # File should not exist at this snapshot
            try:
                os.unlink(file_path)
                files_changed.append(file_path)
            except FileNotFoundError:
                pass  # Already absent
            except OSError as e:
                raise e
            continue

        # File should exist at specific backup version
        if check_origin_file_changed(file_path, backup_file_name):
            _restore_backup(file_path, backup_file_name)
            files_changed.append(file_path)

    return files_changed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

UpdaterFn = Callable[[FileHistoryState], FileHistoryState]


def file_history_track_edit(
    update_state: UpdaterFn,
    file_path: str,
    message_id: str,
) -> None:
    """
    Track a file edit by creating a backup of its current contents.
    Must be called BEFORE the file is actually modified.
    """
    if not file_history_enabled():
        return

    tracking_path = _maybe_shorten_file_path(file_path)

    # Phase 1: capture current state (no-op)
    captured: List[FileHistoryState] = []

    def _capture(state: FileHistoryState) -> FileHistoryState:
        captured.append(state)
        return state

    update_state(_capture)

    if not captured:
        return

    state = captured[0]
    most_recent = state.snapshots[-1] if state.snapshots else None

    if most_recent is None:
        return  # No snapshot to attach to

    if tracking_path in most_recent.tracked_file_backups:
        # Already tracked in most recent snapshot
        return

    # Phase 2: create backup
    try:
        backup = _create_backup(file_path, 1)
    except OSError:
        return

    is_adding_file = backup.backup_file_name is None

    # Phase 3: commit
    def _commit(state: FileHistoryState) -> FileHistoryState:
        most_recent_snapshot = state.snapshots[-1] if state.snapshots else None
        if (most_recent_snapshot is None
                or tracking_path in most_recent_snapshot.tracked_file_backups):
            return state

        updated_tracked_files = set(state.tracked_files)
        updated_tracked_files.add(tracking_path)

        updated_backups = dict(most_recent_snapshot.tracked_file_backups)
        updated_backups[tracking_path] = backup

        updated_snapshot = FileHistorySnapshot(
            message_id=most_recent_snapshot.message_id,
            tracked_file_backups=updated_backups,
            timestamp=most_recent_snapshot.timestamp,
        )

        new_snapshots = list(state.snapshots)
        new_snapshots[-1] = updated_snapshot

        return FileHistoryState(
            snapshots=new_snapshots,
            tracked_files=updated_tracked_files,
            snapshot_sequence=state.snapshot_sequence,
        )

    update_state(_commit)


def file_history_make_snapshot(
    update_state: UpdaterFn,
    message_id: str,
) -> None:
    """
    Create a new snapshot in the file history, backing up any modified tracked files.
    """
    if not file_history_enabled():
        return

    # Phase 1: capture state (no-op)
    captured: List[FileHistoryState] = []

    def _capture(state: FileHistoryState) -> FileHistoryState:
        captured.append(state)
        return state

    update_state(_capture)

    if not captured:
        return

    state = captured[0]
    tracked_file_backups: Dict[str, FileHistoryBackup] = {}
    most_recent_snapshot = state.snapshots[-1] if state.snapshots else None

    if most_recent_snapshot:
        for tracking_path in state.tracked_files:
            file_path = _maybe_expand_file_path(tracking_path)
            latest_backup = most_recent_snapshot.tracked_file_backups.get(tracking_path)
            next_version = (latest_backup.version + 1) if latest_backup else 1

            # Check if file exists
            file_stat: Optional[os.stat_result] = None
            try:
                file_stat = os.stat(file_path)
            except FileNotFoundError:
                pass

            if file_stat is None:
                # File was deleted
                tracked_file_backups[tracking_path] = FileHistoryBackup(
                    backup_file_name=None,
                    version=next_version,
                    backup_time=datetime.now(),
                )
                continue

            # File exists — check if needs new backup
            if (latest_backup
                    and latest_backup.backup_file_name is not None
                    and not check_origin_file_changed(
                        file_path, latest_backup.backup_file_name, file_stat
                    )):
                # Unchanged — reuse
                tracked_file_backups[tracking_path] = latest_backup
                continue

            # Create new backup
            try:
                tracked_file_backups[tracking_path] = _create_backup(file_path, next_version)
            except OSError:
                pass

    # Phase 3: commit the new snapshot
    def _commit(state: FileHistoryState) -> FileHistoryState:
        last_snapshot = state.snapshots[-1] if state.snapshots else None

        # Inherit any backups from tracked files added during phase 2 async window
        if last_snapshot:
            for tracking_path in state.tracked_files:
                if tracking_path not in tracked_file_backups:
                    inherited = last_snapshot.tracked_file_backups.get(tracking_path)
                    if inherited:
                        tracked_file_backups[tracking_path] = inherited

        new_snapshot = FileHistorySnapshot(
            message_id=message_id,
            tracked_file_backups=dict(tracked_file_backups),
            timestamp=datetime.now(),
        )

        all_snapshots = list(state.snapshots) + [new_snapshot]
        if len(all_snapshots) > MAX_SNAPSHOTS:
            all_snapshots = all_snapshots[-MAX_SNAPSHOTS:]

        return FileHistoryState(
            snapshots=all_snapshots,
            tracked_files=set(state.tracked_files),
            snapshot_sequence=(state.snapshot_sequence or 0) + 1,
        )

    update_state(_commit)


def file_history_rewind(
    update_state: UpdaterFn,
    message_id: str,
) -> None:
    """
    Rewind the filesystem to the snapshot associated with message_id.
    Raises ValueError if the snapshot is not found.
    """
    if not file_history_enabled():
        return

    captured: List[FileHistoryState] = []

    def _capture(state: FileHistoryState) -> FileHistoryState:
        captured.append(state)
        return state

    update_state(_capture)
    if not captured:
        return

    state = captured[0]
    # Find the last snapshot for this message_id
    target_snapshot: Optional[FileHistorySnapshot] = None
    for snap in reversed(state.snapshots):
        if snap.message_id == message_id:
            target_snapshot = snap
            break

    if target_snapshot is None:
        raise ValueError(f"FileHistory: Snapshot for {message_id} not found")

    _apply_snapshot(state, target_snapshot)


def file_history_can_restore(state: FileHistoryState, message_id: str) -> bool:
    """Return True if a snapshot for message_id exists in the state."""
    if not file_history_enabled():
        return False
    return any(snap.message_id == message_id for snap in state.snapshots)


def file_history_get_diff_stats(
    state: FileHistoryState, message_id: str
) -> Optional[DiffStats]:
    """
    Compute diff stats (insertions/deletions) for rewinding to message_id's snapshot.
    Returns None if disabled or snapshot not found.
    """
    if not file_history_enabled():
        return None

    target_snapshot: Optional[FileHistorySnapshot] = None
    for snap in reversed(state.snapshots):
        if snap.message_id == message_id:
            target_snapshot = snap
            break

    if target_snapshot is None:
        return None

    files_changed: List[str] = []
    insertions = 0
    deletions = 0

    for tracking_path in state.tracked_files:
        file_path = _maybe_expand_file_path(tracking_path)
        target_backup = target_snapshot.tracked_file_backups.get(tracking_path)

        if target_backup is not None:
            bfn: Any = target_backup.backup_file_name
        else:
            bfn = _get_backup_file_name_first_version(tracking_path, state)
            if bfn is _UNDEFINED_SENTINEL:
                continue

        try:
            if bfn is None:
                # File should not exist — if current file exists, it's changed
                if os.path.exists(file_path):
                    files_changed.append(file_path)
                continue

            diff = _compute_diff_stats_for_file(file_path, bfn)
            if diff.insertions or diff.deletions:
                files_changed.append(file_path)
                insertions += diff.insertions
                deletions += diff.deletions
            elif bfn is None and os.path.exists(file_path):
                files_changed.append(file_path)
        except Exception:
            pass

    return DiffStats(files_changed=files_changed, insertions=insertions, deletions=deletions)


def file_history_has_any_changes(state: FileHistoryState, message_id: str) -> bool:
    """
    Lightweight boolean check: would rewinding to message_id change any file?
    Returns False if disabled or snapshot not found.
    """
    if not file_history_enabled():
        return False

    target_snapshot: Optional[FileHistorySnapshot] = None
    for snap in reversed(state.snapshots):
        if snap.message_id == message_id:
            target_snapshot = snap
            break

    if target_snapshot is None:
        return False

    for tracking_path in state.tracked_files:
        file_path = _maybe_expand_file_path(tracking_path)
        target_backup = target_snapshot.tracked_file_backups.get(tracking_path)

        if target_backup is not None:
            bfn: Any = target_backup.backup_file_name
        else:
            bfn = _get_backup_file_name_first_version(tracking_path, state)
            if bfn is _UNDEFINED_SENTINEL:
                continue

        try:
            if bfn is None:
                if os.path.exists(file_path):
                    return True
                continue
            if check_origin_file_changed(file_path, bfn):
                return True
        except Exception:
            pass

    return False


# ---------------------------------------------------------------------------
# Resume / state restore
# ---------------------------------------------------------------------------

def file_history_restore_state_from_log(
    file_history_snapshots: List[Dict[str, Any]],
    on_update_state: Callable[[FileHistoryState], None],
) -> None:
    """
    Restore FileHistoryState from serialized snapshot log.
    Migrates absolute paths to shortened relative tracking paths.
    """
    if not file_history_enabled():
        return

    snapshots: List[FileHistorySnapshot] = []
    tracked_files: Set[str] = set()

    for raw_snapshot in file_history_snapshots:
        tracked_file_backups: Dict[str, FileHistoryBackup] = {}
        for path, backup_data in raw_snapshot.get("trackedFileBackups", {}).items():
            tracking_path = _maybe_shorten_file_path(path)
            tracked_files.add(tracking_path)
            tracked_file_backups[tracking_path] = FileHistoryBackup(
                backup_file_name=backup_data.get("backupFileName"),
                version=backup_data.get("version", 1),
                backup_time=datetime.fromisoformat(backup_data["backupTime"])
                if isinstance(backup_data.get("backupTime"), str)
                else datetime.now(),
            )
        snapshots.append(FileHistorySnapshot(
            message_id=raw_snapshot.get("messageId", ""),
            tracked_file_backups=tracked_file_backups,
            timestamp=datetime.fromisoformat(raw_snapshot["timestamp"])
            if isinstance(raw_snapshot.get("timestamp"), str)
            else datetime.now(),
        ))

    on_update_state(FileHistoryState(
        snapshots=snapshots,
        tracked_files=tracked_files,
        snapshot_sequence=len(snapshots),
    ))


def copy_file_history_for_resume(log: Dict[str, Any]) -> None:
    """
    Copy file history backup files from a previous session to the current session.
    Used when resuming a previous session.
    """
    if not file_history_enabled():
        return

    file_history_snapshots = log.get("fileHistorySnapshots")
    messages = log.get("messages", [])

    if not file_history_snapshots or not messages:
        return

    last_message = messages[-1]
    previous_session_id = last_message.get("sessionId")

    if not previous_session_id:
        return

    session_id = _get_session_id()
    if previous_session_id == session_id:
        return

    # Create target directory
    config_dir = _get_claude_config_home_dir()
    new_backup_dir = Path(config_dir) / "file-history" / session_id
    new_backup_dir.mkdir(parents=True, exist_ok=True)

    for snapshot in file_history_snapshots:
        for backup_data in snapshot.get("trackedFileBackups", {}).values():
            backup_file_name = backup_data.get("backupFileName")
            if backup_file_name is None:
                continue

            old_backup_path = _resolve_backup_path(backup_file_name, previous_session_id)
            new_backup_path = new_backup_dir / backup_file_name

            if new_backup_path.exists():
                continue

            try:
                # Try hard link first (efficient)
                os.link(str(old_backup_path), str(new_backup_path))
            except FileExistsError:
                pass
            except FileNotFoundError:
                pass  # Source doesn't exist
            except OSError:
                # Fallback to copy
                try:
                    shutil.copy2(str(old_backup_path), str(new_backup_path))
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Legacy FileHistory class (kept for backward compatibility)
# ---------------------------------------------------------------------------

class FileHistory:
    """
    Simple in-memory file edit history supporting snapshot/undo.
    Legacy interface — prefer the module-level functions for full checkpoint support.
    """

    def __init__(self, max_history: int = 50) -> None:
        self._history: Dict[str, List[str]] = {}
        self._max = max_history

    def snapshot(self, path: str, content: str) -> None:
        hist = self._history.setdefault(path, [])
        if hist and hist[-1] == content:
            return
        hist.append(content)
        if len(hist) > self._max:
            hist.pop(0)

    def undo(self, path: str) -> Optional[str]:
        hist = self._history.get(path, [])
        if len(hist) < 2:
            return None
        hist.pop()
        return hist[-1]

    def get_latest(self, path: str) -> Optional[str]:
        hist = self._history.get(path)
        return hist[-1] if hist else None

    def clear(self, path: Optional[str] = None) -> None:
        if path:
            self._history.pop(path, None)
        else:
            self._history.clear()


_history = FileHistory()


def get_file_history() -> FileHistory:
    return _history
