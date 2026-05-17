"""DreamTask. Ported from tasks/DreamTask/DreamTask.ts."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

DreamPhase = str  # 'starting' | 'updating'


@dataclass
class DreamTurn:
    """A single assistant turn from the dream agent."""
    text: str
    tool_use_count: int = 0


@dataclass
class DreamTaskState:
    """State for a DreamTask (memory consolidation sub-agent)."""
    id: str
    type: str = "dream"
    status: str = "running"
    description: str = "dreaming"
    phase: DreamPhase = "starting"
    sessions_reviewing: int = 0
    files_touched: List[str] = field(default_factory=list)
    turns: List[DreamTurn] = field(default_factory=list)
    abort_controller: Optional[Any] = None
    prior_mtime: int = 0
    start_time: float = 0.0
    end_time: Optional[float] = None
    notified: bool = False
    output_file: str = ""
    output_offset: int = 0


# Maximum number of turns to keep in memory for live display.
MAX_TURNS = 30


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

def is_dream_task(task: Any) -> bool:
    """Return True if *task* is a DreamTaskState (or equivalent dict)."""
    if isinstance(task, dict):
        return task.get("type") == "dream"
    return getattr(task, "type", None) == "dream"


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def register_dream_task(
    set_app_state: Callable,
    *,
    sessions_reviewing: int,
    prior_mtime: int,
    abort_controller: Any,
) -> str:
    """
    Register a new DreamTask in app state and return its task ID.

    Mirrors ``registerDreamTask`` from DreamTask.ts.
    """
    import time

    from claude_code.task import generate_task_id, get_task_output_path  # type: ignore[import]

    task_id = generate_task_id("dream")
    output_file = get_task_output_path(task_id)

    task = DreamTaskState(
        id=task_id,
        type="dream",
        status="running",
        description="dreaming",
        phase="starting",
        sessions_reviewing=sessions_reviewing,
        files_touched=[],
        turns=[],
        abort_controller=abort_controller,
        prior_mtime=prior_mtime,
        start_time=time.time() * 1000,
        notified=False,
        output_file=output_file,
        output_offset=0,
    )

    def _register(prev: dict) -> dict:
        tasks = dict(prev.get("tasks") or {})
        tasks[task_id] = task
        return {**prev, "tasks": tasks}

    set_app_state(_register)
    return task_id


def add_dream_turn(
    task_id: str,
    turn: DreamTurn,
    touched_paths: List[str],
    set_app_state: Callable,
) -> None:
    """
    Append a turn to the DreamTask and update touched file list.
    Mirrors ``addDreamTurn`` from DreamTask.ts.
    """
    def _update(prev: dict) -> dict:
        tasks = dict(prev.get("tasks") or {})
        task = tasks.get(task_id)
        if task is None:
            return prev
        if isinstance(task, DreamTaskState):
            seen = set(task.files_touched)
            new_touched = [p for p in touched_paths if p not in seen]
            # Skip no-op updates
            if not turn.text and not turn.tool_use_count and not new_touched:
                return prev
            new_phase: DreamPhase = "updating" if new_touched else task.phase
            new_files = task.files_touched + new_touched if new_touched else task.files_touched
            # Keep only the last MAX_TURNS turns
            new_turns = task.turns[-(MAX_TURNS - 1):] + [turn]
            updated = DreamTaskState(
                **{**task.__dict__, "phase": new_phase, "files_touched": new_files, "turns": new_turns}
            )
            tasks[task_id] = updated
        elif isinstance(task, dict):
            seen = set(task.get("files_touched") or [])
            new_touched = [p for p in touched_paths if p not in seen]
            if not turn.text and not turn.tool_use_count and not new_touched:
                return prev
            tasks[task_id] = {
                **task,
                "phase": "updating" if new_touched else task.get("phase", "starting"),
                "files_touched": (task.get("files_touched") or []) + new_touched,
                "turns": ((task.get("turns") or [])[-(MAX_TURNS - 1):]) + [turn.__dict__],
            }
        return {**prev, "tasks": tasks}

    set_app_state(_update)


def complete_dream_task(task_id: str, set_app_state: Callable) -> None:
    """Mark a DreamTask as completed. Mirrors ``completeDreamTask``."""
    import time

    def _update(prev: dict) -> dict:
        tasks = dict(prev.get("tasks") or {})
        task = tasks.get(task_id)
        if task is None:
            return prev
        if isinstance(task, DreamTaskState):
            tasks[task_id] = DreamTaskState(
                **{**task.__dict__, "status": "completed", "end_time": time.time() * 1000,
                   "notified": True, "abort_controller": None}
            )
        elif isinstance(task, dict):
            tasks[task_id] = {**task, "status": "completed", "end_time": time.time() * 1000,
                              "notified": True, "abort_controller": None}
        return {**prev, "tasks": tasks}

    set_app_state(_update)


def fail_dream_task(task_id: str, set_app_state: Callable) -> None:
    """Mark a DreamTask as failed. Mirrors ``failDreamTask``."""
    import time

    def _update(prev: dict) -> dict:
        tasks = dict(prev.get("tasks") or {})
        task = tasks.get(task_id)
        if task is None:
            return prev
        if isinstance(task, DreamTaskState):
            tasks[task_id] = DreamTaskState(
                **{**task.__dict__, "status": "failed", "end_time": time.time() * 1000,
                   "notified": True, "abort_controller": None}
            )
        elif isinstance(task, dict):
            tasks[task_id] = {**task, "status": "failed", "end_time": time.time() * 1000,
                              "notified": True, "abort_controller": None}
        return {**prev, "tasks": tasks}

    set_app_state(_update)


# ---------------------------------------------------------------------------
# Task descriptor (matches Task protocol)
# ---------------------------------------------------------------------------

class DreamTask:
    """Task descriptor for the dream (memory consolidation) agent task."""

    type = "dream"
    name = "DreamTask"

    @classmethod
    async def kill(cls, task_id: str, set_app_state: Callable) -> None:
        """
        Kill a running DreamTask.

        Aborts the abort controller, marks status as 'killed', and rolls
        back the consolidation lock so the next session can retry.
        Mirrors ``DreamTask.kill`` from DreamTask.ts.
        """
        import time

        prior_mtime: Optional[int] = None

        def _update(prev: dict) -> dict:
            nonlocal prior_mtime
            tasks = dict(prev.get("tasks") or {})
            task = tasks.get(task_id)
            if task is None:
                return prev
            if isinstance(task, DreamTaskState):
                if task.status != "running":
                    return prev
                if task.abort_controller is not None:
                    try:
                        task.abort_controller.abort()
                    except Exception:
                        pass
                prior_mtime = task.prior_mtime
                tasks[task_id] = DreamTaskState(
                    **{**task.__dict__, "status": "killed",
                       "end_time": time.time() * 1000, "notified": True,
                       "abort_controller": None}
                )
            elif isinstance(task, dict):
                if task.get("status") != "running":
                    return prev
                ac = task.get("abort_controller")
                if ac and hasattr(ac, "abort"):
                    try:
                        ac.abort()
                    except Exception:
                        pass
                prior_mtime = task.get("prior_mtime")
                tasks[task_id] = {**task, "status": "killed",
                                  "end_time": time.time() * 1000,
                                  "notified": True, "abort_controller": None}
            return {**prev, "tasks": tasks}

        set_app_state(_update)

        # Roll back the consolidation lock so the next session can retry.
        if prior_mtime is not None:
            try:
                from claude_code.services.auto_dream.consolidation_lock import (  # type: ignore[import]
                    rollback_consolidation_lock,
                )
                await rollback_consolidation_lock(prior_mtime)
            except (ImportError, Exception) as exc:
                logger.debug("rollback_consolidation_lock skipped: %s", exc)
