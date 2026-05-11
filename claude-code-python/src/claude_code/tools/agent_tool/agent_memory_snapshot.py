"""Agent memory snapshot utilities. Ported from AgentTool/agentMemorySnapshot.ts"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Literal, Optional, TypedDict

SNAPSHOT_BASE = "agent-memory-snapshots"
SNAPSHOT_JSON = "snapshot.json"
SYNCED_JSON = ".snapshot-synced.json"


class SnapshotMeta(TypedDict):
    updatedAt: str


class SyncedMeta(TypedDict):
    syncedFrom: str


# ---------------------------------------------------------------------------
# Scope helpers (mirrors agentMemory.ts / getAgentMemoryDir)
# ---------------------------------------------------------------------------
AgentMemoryScope = Literal["session", "project", "global"]


def _get_cwd() -> str:
    try:
        from claude_code.utils.cwd import get_cwd  # type: ignore[import]
        return get_cwd()
    except Exception:
        return os.getcwd()


def get_agent_memory_dir(agent_type: str, scope: AgentMemoryScope) -> str:
    """Return the local agent memory directory for a given agent type and scope."""
    if scope == "project":
        return os.path.join(_get_cwd(), ".claude", "agent-memory", agent_type)
    if scope == "global":
        return os.path.join(os.path.expanduser("~"), ".claude", "agent-memory", agent_type)
    # session scope — per-run temp dir
    return os.path.join(
        os.environ.get("TMPDIR", "/tmp"),
        "claude-agent-memory",
        agent_type,
    )


def get_snapshot_dir_for_agent(agent_type: str) -> str:
    """Return the snapshot directory path for an agent in the current project."""
    return os.path.join(_get_cwd(), ".claude", SNAPSHOT_BASE, agent_type)


def _snapshot_json_path(agent_type: str) -> str:
    return os.path.join(get_snapshot_dir_for_agent(agent_type), SNAPSHOT_JSON)


def _synced_json_path(agent_type: str, scope: AgentMemoryScope) -> str:
    return os.path.join(get_agent_memory_dir(agent_type, scope), SYNCED_JSON)


def _read_json_file(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.loads(fh.read())
    except Exception:
        return None


async def _copy_snapshot_to_local(agent_type: str, scope: AgentMemoryScope) -> None:
    """Copy snapshot memory files to the local agent memory directory."""
    import aiofiles  # type: ignore[import]
    import asyncio

    snapshot_dir = get_snapshot_dir_for_agent(agent_type)
    local_dir = get_agent_memory_dir(agent_type, scope)
    os.makedirs(local_dir, exist_ok=True)

    try:
        for entry in os.scandir(snapshot_dir):
            if entry.is_file() and entry.name != SNAPSHOT_JSON:
                src = entry.path
                dst = os.path.join(local_dir, entry.name)
                try:
                    async with aiofiles.open(src, encoding="utf-8") as f:
                        content = await f.read()
                    async with aiofiles.open(dst, "w", encoding="utf-8") as f:
                        await f.write(content)
                except Exception:
                    pass
    except Exception:
        pass


async def _save_synced_meta(
    agent_type: str, scope: AgentMemoryScope, snapshot_timestamp: str
) -> None:
    """Persist the synced-from timestamp so we can detect newer snapshots."""
    import aiofiles  # type: ignore[import]

    local_dir = get_agent_memory_dir(agent_type, scope)
    os.makedirs(local_dir, exist_ok=True)
    synced_path = _synced_json_path(agent_type, scope)
    meta: SyncedMeta = {"syncedFrom": snapshot_timestamp}
    try:
        async with aiofiles.open(synced_path, "w", encoding="utf-8") as fh:
            await fh.write(json.dumps(meta))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SnapshotCheckResult(TypedDict):
    action: Literal["none", "initialize", "prompt-update"]
    snapshotTimestamp: Optional[str]


async def check_agent_memory_snapshot(
    agent_type: str, scope: AgentMemoryScope
) -> SnapshotCheckResult:
    """Check if a snapshot exists and whether it is newer than what was last synced."""
    snapshot_meta = _read_json_file(_snapshot_json_path(agent_type))
    if not snapshot_meta or "updatedAt" not in snapshot_meta:
        return {"action": "none", "snapshotTimestamp": None}

    snapshot_ts: str = snapshot_meta["updatedAt"]
    local_dir = get_agent_memory_dir(agent_type, scope)

    has_local = False
    try:
        has_local = any(
            e.name.endswith(".md") for e in os.scandir(local_dir) if e.is_file()
        )
    except OSError:
        pass

    if not has_local:
        return {"action": "initialize", "snapshotTimestamp": snapshot_ts}

    synced_meta = _read_json_file(_synced_json_path(agent_type, scope))
    if not synced_meta or "syncedFrom" not in synced_meta:
        return {"action": "prompt-update", "snapshotTimestamp": snapshot_ts}

    from datetime import datetime, timezone

    try:
        snap_dt = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
        sync_dt = datetime.fromisoformat(synced_meta["syncedFrom"].replace("Z", "+00:00"))
        if snap_dt > sync_dt:
            return {"action": "prompt-update", "snapshotTimestamp": snapshot_ts}
    except Exception:
        pass

    return {"action": "none", "snapshotTimestamp": None}


async def initialize_from_snapshot(
    agent_type: str, scope: AgentMemoryScope, snapshot_timestamp: str
) -> None:
    """Initialize local agent memory from a snapshot (first-time setup)."""
    await _copy_snapshot_to_local(agent_type, scope)
    await _save_synced_meta(agent_type, scope, snapshot_timestamp)


async def replace_from_snapshot(
    agent_type: str, scope: AgentMemoryScope, snapshot_timestamp: str
) -> None:
    """Replace local agent memory with the snapshot, removing orphaned files."""
    local_dir = get_agent_memory_dir(agent_type, scope)
    try:
        for entry in os.scandir(local_dir):
            if entry.is_file() and entry.name.endswith(".md"):
                os.unlink(entry.path)
    except OSError:
        pass
    await _copy_snapshot_to_local(agent_type, scope)
    await _save_synced_meta(agent_type, scope, snapshot_timestamp)


async def mark_snapshot_synced(
    agent_type: str, scope: AgentMemoryScope, snapshot_timestamp: str
) -> None:
    """Mark the current snapshot as synced without changing local memory."""
    await _save_synced_meta(agent_type, scope, snapshot_timestamp)
