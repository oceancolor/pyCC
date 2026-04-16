"""
Cron scheduler core for scheduled tasks.
Ported from cronScheduler.ts — simplified Python version using asyncio.
Supports cron expressions (via croniter if available), interval-based,
and one-shot 'at' scheduling.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Try to import croniter for proper cron expression support
try:
    from croniter import croniter as _croniter  # type: ignore
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False
    logger.debug("croniter not available; falling back to interval-based scheduling")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CronSchedule:
    """Schedule specification: cron expression, interval in seconds, or ISO timestamp."""
    cron: Optional[str] = None          # e.g. "*/5 * * * *"
    interval_seconds: Optional[float] = None  # e.g. 300.0
    at: Optional[str] = None            # ISO-8601 one-shot, e.g. "2024-01-01T09:00:00Z"


@dataclass
class CronJob:
    """A scheduled job definition."""
    id: str
    name: str
    schedule: CronSchedule
    payload: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_fired_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "schedule": {
                "cron": self.schedule.cron,
                "interval_seconds": self.schedule.interval_seconds,
                "at": self.schedule.at,
            },
            "payload": self.payload,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_fired_at": self.last_fired_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CronJob":
        sched = data.get("schedule", {})
        return cls(
            id=data["id"],
            name=data["name"],
            schedule=CronSchedule(
                cron=sched.get("cron"),
                interval_seconds=sched.get("interval_seconds"),
                at=sched.get("at"),
            ),
            payload=data.get("payload", {}),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", time.time()),
            last_fired_at=data.get("last_fired_at"),
        )


# ---------------------------------------------------------------------------
# Next-fire computation helpers
# ---------------------------------------------------------------------------

def _next_fire_for_job(job: CronJob, now: float) -> Optional[float]:
    """Return epoch seconds for the next fire of *job*, or None if never."""
    s = job.schedule

    if s.at:
        # One-shot: parse ISO timestamp
        try:
            dt = datetime.fromisoformat(s.at.replace("Z", "+00:00"))
            ts = dt.timestamp()
            return ts if ts > now else None
        except ValueError:
            logger.warning("Invalid 'at' timestamp for job %s: %s", job.id, s.at)
            return None

    if s.interval_seconds and s.interval_seconds > 0:
        anchor = job.last_fired_at if job.last_fired_at else job.created_at
        next_ts = anchor + s.interval_seconds
        # If already overdue, fire now (next tick)
        return max(next_ts, now)

    if s.cron:
        if HAS_CRONITER:
            try:
                base = job.last_fired_at if job.last_fired_at else now
                ci = _croniter(s.cron, datetime.fromtimestamp(base, tz=timezone.utc))
                return ci.get_next(float)
            except Exception as exc:
                logger.warning("croniter error for job %s: %s", job.id, exc)
                return None
        else:
            # Fallback: treat cron as 60s interval
            anchor = job.last_fired_at if job.last_fired_at else job.created_at
            return max(anchor + 60.0, now)

    return None


# ---------------------------------------------------------------------------
# CronScheduler
# ---------------------------------------------------------------------------

class CronScheduler:
    """
    Asyncio-based cron scheduler.

    Usage::

        scheduler = CronScheduler(on_fire=my_handler)
        scheduler.add_job(CronJob(...))
        await scheduler.start()
        ...
        await scheduler.stop()
    """

    def __init__(
        self,
        on_fire: Callable[[CronJob], Any],
        tick_interval: float = 1.0,
        tasks_file: Optional[Union[str, Path]] = None,
    ) -> None:
        self._on_fire = on_fire
        self._tick_interval = tick_interval
        self._tasks_file = Path(tasks_file) if tasks_file else None
        self._jobs: Dict[str, CronJob] = {}
        self._next_fire: Dict[str, float] = {}   # job_id → epoch seconds
        self._in_flight: set = set()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def add_job(self, job: CronJob) -> None:
        """Register a new job (or replace an existing one with same id)."""
        self._jobs[job.id] = job
        self._next_fire.pop(job.id, None)  # recompute on next tick
        logger.debug("Added job %s (%s)", job.id, job.name)

    def remove_job(self, job_id: str) -> bool:
        """Remove a job. Returns True if it existed."""
        existed = job_id in self._jobs
        self._jobs.pop(job_id, None)
        self._next_fire.pop(job_id, None)
        return existed

    def list_jobs(self) -> List[CronJob]:
        """Return all registered jobs."""
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> Optional[CronJob]:
        return self._jobs.get(job_id)

    # ------------------------------------------------------------------
    # Manual execution
    # ------------------------------------------------------------------

    async def run_job(self, job_id: str) -> bool:
        """Manually trigger a job immediately. Returns False if not found."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        await self._fire(job)
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        if self._tasks_file:
            await self._load_tasks_file()
        self._task = asyncio.create_task(self._loop(), name="cron-scheduler")
        logger.info("CronScheduler started")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("CronScheduler stopped")

    def get_next_fire_time(self) -> Optional[float]:
        """Earliest scheduled fire epoch seconds, or None."""
        values = [v for v in self._next_fire.values() if v != float("inf")]
        return min(values) if values else None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            await self._check()
            await asyncio.sleep(self._tick_interval)

    async def _check(self) -> None:
        now = time.time()
        to_remove: List[str] = []

        for job_id, job in list(self._jobs.items()):
            if not job.enabled or job_id in self._in_flight:
                continue

            # Compute next fire if not cached
            if job_id not in self._next_fire:
                nf = _next_fire_for_job(job, now)
                if nf is None:
                    # One-shot already expired or bad schedule
                    to_remove.append(job_id)
                    continue
                self._next_fire[job_id] = nf

            if now >= self._next_fire[job_id]:
                is_one_shot = bool(job.schedule.at) or (
                    not job.schedule.cron and not job.schedule.interval_seconds
                )
                await self._fire(job)
                if is_one_shot:
                    to_remove.append(job_id)
                else:
                    # Reschedule from now
                    job.last_fired_at = now
                    nf = _next_fire_for_job(job, now)
                    self._next_fire[job_id] = nf if nf is not None else float("inf")

        for job_id in to_remove:
            self._jobs.pop(job_id, None)
            self._next_fire.pop(job_id, None)

    async def _fire(self, job: CronJob) -> None:
        self._in_flight.add(job.id)
        try:
            result = self._on_fire(job)
            if asyncio.iscoroutine(result):
                await result
            job.last_fired_at = time.time()
            logger.debug("Fired job %s", job.id)
        except Exception as exc:
            logger.error("Job %s raised an exception: %s", job.id, exc)
        finally:
            self._in_flight.discard(job.id)

    async def _load_tasks_file(self) -> None:
        if not self._tasks_file or not self._tasks_file.exists():
            return
        try:
            data = json.loads(self._tasks_file.read_text(encoding="utf-8"))
            for item in data if isinstance(data, list) else []:
                job = CronJob.from_dict(item)
                self._jobs[job.id] = job
            logger.debug("Loaded %d tasks from %s", len(self._jobs), self._tasks_file)
        except Exception as exc:
            logger.warning("Failed to load tasks file %s: %s", self._tasks_file, exc)

    async def save_tasks_file(self) -> None:
        if not self._tasks_file:
            return
        self._tasks_file.parent.mkdir(parents=True, exist_ok=True)
        data = [j.to_dict() for j in self._jobs.values()]
        self._tasks_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
