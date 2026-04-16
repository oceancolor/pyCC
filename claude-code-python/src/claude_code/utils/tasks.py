"""Task management system for Claude Code Python port."""
from __future__ import annotations

import asyncio, json, os, re
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

TASK_STATUSES = ("pending", "in_progress", "completed")
HIGH_WATER_MARK_FILE = ".highwatermark"

_STATUS_MIGRATE = {
    "open": "pending", "resolved": "completed",
    "planning": "in_progress", "implementing": "in_progress",
    "reviewing": "in_progress", "verifying": "in_progress",
}


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class Task:
    id: str
    subject: str
    description: str
    status: TaskStatus
    blocks: List[str] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)
    active_form: Optional[str] = None
    owner: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["blockedBy"] = d.pop("blocked_by")
        d["activeForm"] = d.pop("active_form")
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        raw = _STATUS_MIGRATE.get(data.get("status", "pending"), data.get("status", "pending"))
        return cls(
            id=data["id"],
            subject=data.get("subject", data.get("description", "")),
            description=data.get("description", ""),
            status=TaskStatus(raw),
            blocks=data.get("blocks", []),
            blocked_by=data.get("blockedBy", data.get("blocked_by", [])),
            active_form=data.get("activeForm", data.get("active_form")),
            owner=data.get("owner"),
            metadata=data.get("metadata"),
        )


# ── Path helpers ────────────────────────────────────────────────────────────

def _cfg_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_HOME", Path.home() / ".claude"))

def _sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", s)

def _tasks_dir(tid: str) -> Path:
    return _cfg_home() / "tasks" / _sanitize(tid)

def _task_path(tid: str, task_id: str) -> Path:
    return _tasks_dir(tid) / f"{_sanitize(task_id)}.json"

def _hwm_path(tid: str) -> Path:
    return _tasks_dir(tid) / HIGH_WATER_MARK_FILE


# ── High-water mark ──────────────────────────────────────────────────────────

async def _read_hwm(tid: str) -> int:
    try:
        return int(_hwm_path(tid).read_text().strip())
    except Exception:
        return 0

async def _write_hwm(tid: str, v: int) -> None:
    _hwm_path(tid).write_text(str(v))

async def _highest_id(tid: str) -> int:
    d = _tasks_dir(tid)
    hi = 0
    try:
        for f in d.iterdir():
            if f.suffix == ".json" and not f.name.startswith("."):
                try:
                    n = int(f.stem)
                    hi = max(hi, n)
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return max(hi, await _read_hwm(tid))


# ── In-process locks (per task-list) ────────────────────────────────────────

_LOCKS: Dict[str, asyncio.Lock] = {}

def _lock(key: str) -> asyncio.Lock:
    if key not in _LOCKS:
        _LOCKS[key] = asyncio.Lock()
    return _LOCKS[key]


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def create_task(tid: str, data: Dict[str, Any]) -> str:
    _tasks_dir(tid).mkdir(parents=True, exist_ok=True)
    async with _lock(tid):
        new_id = str(await _highest_id(tid) + 1)
        # Accept only known Task fields
        known = {f for f in Task.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        task = Task(id=new_id, **filtered)  # type: ignore[arg-type]
        _task_path(tid, new_id).write_text(json.dumps(task.to_dict(), indent=2))
    return new_id


async def get_task(tid: str, task_id: str) -> Optional[Task]:
    try:
        return Task.from_dict(json.loads(_task_path(tid, task_id).read_text()))
    except Exception:
        return None


async def update_task(tid: str, task_id: str, updates: Dict[str, Any]) -> Optional[Task]:
    async with _lock(f"{tid}:{task_id}"):
        existing = await get_task(tid, task_id)
        if existing is None:
            return None
        d = existing.to_dict()
        d.update(updates)
        d["id"] = task_id
        updated = Task.from_dict(d)
        _task_path(tid, task_id).write_text(json.dumps(updated.to_dict(), indent=2))
    return updated


async def delete_task(tid: str, task_id: str) -> bool:
    path = _task_path(tid, task_id)
    try:
        try:
            n = int(task_id)
            if n > await _read_hwm(tid):
                await _write_hwm(tid, n)
        except ValueError:
            pass
        path.unlink()
        for t in await list_tasks(tid):
            nb, nbb = [b for b in t.blocks if b != task_id], [b for b in t.blocked_by if b != task_id]
            if nb != t.blocks or nbb != t.blocked_by:
                await update_task(tid, t.id, {"blocks": nb, "blockedBy": nbb})
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


async def list_tasks(tid: str) -> List[Task]:
    try:
        files = list(_tasks_dir(tid).iterdir())
    except FileNotFoundError:
        return []
    results = []
    for f in files:
        if f.suffix == ".json" and not f.name.startswith("."):
            t = await get_task(tid, f.stem)
            if t:
                results.append(t)
    return results


async def update_task_status(tid: str, task_id: str, status: TaskStatus) -> Optional[Task]:
    return await update_task(tid, task_id, {"status": status.value})


# ── TaskStore ────────────────────────────────────────────────────────────────

class TaskStore:
    """Session-scoped task store facade."""

    def __init__(self, task_list_id: str) -> None:
        self.task_list_id = task_list_id

    async def create(self, data: Dict[str, Any]) -> str:
        return await create_task(self.task_list_id, data)

    async def get(self, task_id: str) -> Optional[Task]:
        return await get_task(self.task_list_id, task_id)

    async def list(self) -> List[Task]:
        return await list_tasks(self.task_list_id)

    async def update_status(self, task_id: str, status: TaskStatus) -> Optional[Task]:
        return await update_task_status(self.task_list_id, task_id, status)

    async def delete(self, task_id: str) -> bool:
        return await delete_task(self.task_list_id, task_id)


_task_store: Optional[TaskStore] = None


def get_task_store(task_list_id: Optional[str] = None) -> TaskStore:
    """Return the session-level TaskStore singleton."""
    global _task_store
    if _task_store is None:
        tid = task_list_id or os.environ.get("CLAUDE_CODE_TASK_LIST_ID", "default")
        _task_store = TaskStore(tid)
    return _task_store
