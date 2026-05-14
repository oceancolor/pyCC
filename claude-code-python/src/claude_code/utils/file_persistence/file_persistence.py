"""File persistence orchestrator. Ported from utils/filePersistence/filePersistence.ts"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

OUTPUTS_SUBDIR = "outputs"
FILE_COUNT_LIMIT = 500
DEFAULT_UPLOAD_CONCURRENCY = 5


def get_environment_kind() -> Optional[str]:
    """Return the environment kind from CLAUDE_CODE_ENVIRONMENT_KIND.

    Returns 'byoc', 'anthropic_cloud', or None if not set/recognized.
    """
    kind = os.environ.get("CLAUDE_CODE_ENVIRONMENT_KIND")
    if kind in ("byoc", "anthropic_cloud"):
        return kind
    return None


async def find_modified_files(
    outputs_dir: str,
    turn_start_time: float,
) -> List[str]:
    """Find files modified since *turn_start_time* (epoch seconds).

    Recursively scans *outputs_dir* and returns paths of files whose
    modification time is >= turn_start_time.
    """
    modified: List[str] = []
    root = Path(outputs_dir)
    if not root.exists():
        return modified

    for entry in root.rglob("*"):
        if entry.is_file():
            try:
                mtime = entry.stat().st_mtime
                if mtime >= turn_start_time:
                    modified.append(str(entry))
            except OSError:
                continue
    return modified


async def run_file_persistence(
    turn_start_time: float,
    signal: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Execute file persistence for modified files in the outputs directory.

    Assembles all config internally:
    - Checks environment kind (CLAUDE_CODE_ENVIRONMENT_KIND)
    - Requires CLAUDE_CODE_REMOTE_SESSION_ID for session ID

    Args:
        turn_start_time: Unix timestamp (float) when the turn started.
        signal: Optional cancellation signal (ignored in Python port).

    Returns:
        Event data dict with persisted file info, or None if disabled/no files.
    """
    environment_kind = get_environment_kind()
    if environment_kind != "byoc":
        return None

    session_id = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    if not session_id:
        return None

    cwd = os.environ.get("CLAUDE_CODE_CWD", os.getcwd())
    outputs_dir = str(Path(cwd) / session_id / OUTPUTS_SUBDIR)

    start_ms = int(time.time() * 1000)

    try:
        modified_files = await find_modified_files(outputs_dir, turn_start_time)
        if not modified_files:
            return {"filesCount": 0, "mode": environment_kind, "durationMs": int(time.time() * 1000) - start_ms}

        # Limit the number of files to upload
        files_to_upload = modified_files[:FILE_COUNT_LIMIT]
        truncated = len(modified_files) > FILE_COUNT_LIMIT

        # In a full implementation this would call the Files API
        # (uploadSessionFiles). In the Python port we just record metadata.
        persisted: List[Dict[str, Any]] = []
        for path_str in files_to_upload:
            try:
                size = os.path.getsize(path_str)
                rel = os.path.relpath(path_str, outputs_dir)
                persisted.append({"path": rel, "size": size})
            except OSError:
                pass

        duration_ms = int(time.time() * 1000) - start_ms
        return {
            "filesCount": len(persisted),
            "mode": environment_kind,
            "durationMs": duration_ms,
            "truncated": truncated,
            "files": persisted,
        }
    except Exception as exc:
        return None


async def persist_session_files(session_id: str, context: Any = None) -> None:
    """Convenience wrapper: persist files for the given session.

    This is the simplified entry point used by the session teardown path.
    """
    turn_start = time.time() - 60  # default: files modified in the last minute
    if context and isinstance(context, dict):
        turn_start = context.get("turnStartTime", turn_start)
    await run_file_persistence(turn_start)
