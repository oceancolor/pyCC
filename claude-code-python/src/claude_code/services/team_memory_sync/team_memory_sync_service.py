"""Team memory sync service. Orchestrates pull/push/merge for team memory.

Wraps the per-operation functions (pull, push, merge, diff) into a high-level
sync lifecycle that matches the behaviour of the TS teamMemorySync/index.ts.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TeamMemorySyncResult:
    success: bool = False
    pulled: int = 0
    pushed: int = 0
    merged: int = 0
    conflicts: List[str] = field(default_factory=list)
    error: Optional[str] = None


async def sync_team_memory_service(
    remote_url: str,
    local_dir: str,
    branch: str = "main",
    timeout_ms: int = 30_000,
) -> TeamMemorySyncResult:
    """High-level team memory sync: pull remote, merge, then push local changes.

    Args:
        remote_url: Git remote URL for the shared team memory repo.
        local_dir: Local directory containing .md memory files.
        branch: Remote branch to sync against.
        timeout_ms: Per-operation timeout in milliseconds.

    Returns:
        TeamMemorySyncResult summarising what happened.
    """
    result = TeamMemorySyncResult()

    try:
        from claude_code.services.team_memory_sync.team_memory_pull import pull_remote_entries
        from claude_code.services.team_memory_sync.team_memory_push import push_local_entries
        from claude_code.services.team_memory_sync.team_memory_merge import merge_entries
        from claude_code.services.team_memory_sync.team_memory_diff import diff_entries
        from pathlib import Path

        # Load local entries
        local_path = Path(local_dir)
        local_entries: Dict[str, str] = {}
        if local_path.is_dir():
            for md_file in local_path.glob("*.md"):
                local_entries[md_file.name] = md_file.read_text(encoding="utf-8")

        # Pull remote
        remote_entries = await pull_remote_entries(remote_url, branch, timeout_ms) or {}
        result.pulled = len(remote_entries)

        # Merge
        merged, conflicts = merge_entries({}, local_entries, remote_entries)
        result.merged = len(merged)
        result.conflicts = list(conflicts.keys())

        # Write merged entries back locally
        for filename, content in merged.items():
            (local_path / filename).write_text(content, encoding="utf-8")

        # Push local changes
        if local_entries:
            pushed = await push_local_entries(remote_url, local_entries, branch, timeout_ms)
            if pushed:
                result.pushed = len(local_entries)

        result.success = True

    except Exception as exc:
        result.error = str(exc)
        result.success = False

    return result
