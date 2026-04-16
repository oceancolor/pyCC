"""Heap dump service — Python port of heapDumpService.ts.

Uses tracemalloc + resource stats instead of V8 heap snapshots.
Writes JSON diagnostics and a lightweight allocation snapshot to disk.
"""

from __future__ import annotations

import json
import platform
import resource
import sys
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional


@dataclass
class HeapDumpConfig:
    """Configuration for heap dump behaviour."""
    output_dir: str = ""
    top_n_frames: int = 20
    include_traceback: bool = True


@dataclass
class MemoryDiagnostics:
    """Memory diagnostics captured at dump time."""
    timestamp: str
    trigger: Literal["manual", "auto-threshold"]
    dump_number: int
    uptime_seconds: float
    heap_used_bytes: int
    heap_peak_bytes: int
    rss_bytes: int
    top_allocations: list[dict]
    analysis: dict[str, object]
    platform: str
    python_version: str


@dataclass
class HeapDumpResult:
    """Result returned by trigger_heap_dump."""
    success: bool
    diag_path: Optional[str] = None
    snapshot_path: Optional[str] = None
    error: Optional[str] = None


_start_time: float = time.monotonic()
_tracemalloc_started: bool = False


def _ensure_tracemalloc() -> None:
    global _tracemalloc_started
    if not _tracemalloc_started:
        tracemalloc.start(25)
        _tracemalloc_started = True


def _get_rss_bytes() -> int:
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss * 1024 if sys.platform == "linux" else usage.ru_maxrss
    except Exception:
        return 0


def _capture_diagnostics(
    trigger: Literal["manual", "auto-threshold"],
    dump_number: int,
    top_n: int,
) -> MemoryDiagnostics:
    _ensure_tracemalloc()
    current, peak = tracemalloc.get_traced_memory()
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")[:top_n]
    top_allocs = [
        {
            "file": str(stat.traceback[0].filename) if stat.traceback else "?",
            "line": stat.traceback[0].lineno if stat.traceback else 0,
            "size_bytes": stat.size,
            "count": stat.count,
        }
        for stat in top_stats
    ]
    rss = _get_rss_bytes()
    uptime = time.monotonic() - _start_time
    potential_leaks: list[str] = []
    if current > 500 * 1024 * 1024:
        potential_leaks.append(f"High heap usage: {current / 1024 / 1024:.1f} MB traced")
    if rss > 2 * 1024 * 1024 * 1024:
        potential_leaks.append(f"High RSS: {rss / 1024 / 1024:.1f} MB")
    analysis: dict[str, object] = {
        "potential_leaks": potential_leaks,
        "recommendation": (
            f"WARNING: {len(potential_leaks)} indicator(s) found."
            if potential_leaks else "No obvious leak indicators."
        ),
    }
    return MemoryDiagnostics(
        timestamp=datetime.now(timezone.utc).isoformat(),
        trigger=trigger,
        dump_number=dump_number,
        uptime_seconds=round(uptime, 2),
        heap_used_bytes=current,
        heap_peak_bytes=peak,
        rss_bytes=rss,
        top_allocations=top_allocs,
        analysis=analysis,
        platform=platform.platform(),
        python_version=sys.version,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def trigger_heap_dump(
    output_dir: str = "",
    config: Optional[HeapDumpConfig] = None,
    trigger: Literal["manual", "auto-threshold"] = "manual",
    dump_number: int = 0,
) -> HeapDumpResult:
    """
    Capture memory diagnostics and an allocation snapshot.

    Parameters
    ----------
    output_dir:
        Directory to write files into. Defaults to home dir.
    config:
        Optional :class:`HeapDumpConfig` to override defaults.
    trigger:
        ``"manual"`` or ``"auto-threshold"``.
    dump_number:
        Sequential dump index (0 for manual).

    Returns
    -------
    HeapDumpResult
        Paths to written files and success flag.
    """
    cfg = config or HeapDumpConfig(output_dir=output_dir)
    target_dir = Path(cfg.output_dir or output_dir or Path.home()).expanduser()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        diag = _capture_diagnostics(trigger, dump_number, cfg.top_n_frames)
        suffix = f"-dump{dump_number}" if dump_number > 0 else ""
        ts_tag = datetime.now().strftime("%Y%m%dT%H%M%S")
        diag_path = target_dir / f"heap{suffix}-{ts_tag}-diagnostics.json"
        diag_path.write_text(json.dumps(diag.__dict__, indent=2, default=str), encoding="utf-8")
        snap_path = target_dir / f"heap{suffix}-{ts_tag}-snapshot.json"
        snap_path.write_text(
            json.dumps(
                {"timestamp": diag.timestamp, "top_allocations": diag.top_allocations,
                 "heap_used_bytes": diag.heap_used_bytes, "heap_peak_bytes": diag.heap_peak_bytes},
                indent=2,
            ),
            encoding="utf-8",
        )
        return HeapDumpResult(success=True, diag_path=str(diag_path), snapshot_path=str(snap_path))
    except Exception as exc:  # noqa: BLE001
        return HeapDumpResult(success=False, error=str(exc))
