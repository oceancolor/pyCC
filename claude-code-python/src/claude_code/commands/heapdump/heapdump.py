"""
Ported from: commands/heapdump/heapdump.ts

/heapdump command — trigger a heap dump (and optional diagnostic snapshot)
of the running process.  In the Python port we collect memory diagnostics
using the ``tracemalloc`` standard-library module and write the result to a
timestamped file under the Claude data directory, mirroring the behaviour of
``performHeapDump()`` in the TS source.
"""
from __future__ import annotations

import os
import time
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Core heap-dump logic
# ---------------------------------------------------------------------------

def _get_dump_dir() -> str:
    """Return the directory where dump files are written."""
    return os.path.join(os.path.expanduser("~"), ".claude", "heapdumps")


def _perform_heap_dump() -> Dict[str, object]:
    """
    Collect a memory snapshot and write it to disk.

    Returns a result dict with keys:
      success  : bool
      heap_path: str  (only when success is True)
      diag_path: str  (only when success is True)
      error    : str  (only when success is False)
    """
    import tracemalloc
    import json

    dump_dir = _get_dump_dir()
    os.makedirs(dump_dir, exist_ok=True)

    ts = int(time.time() * 1000)
    heap_path = os.path.join(dump_dir, f"heap-{ts}.json")
    diag_path = os.path.join(dump_dir, f"diag-{ts}.json")

    try:
        # Start (or resume) tracemalloc tracing
        if not tracemalloc.is_tracing():
            tracemalloc.start()

        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")

        heap_data = [
            {
                "file": str(stat.traceback),
                "size_bytes": stat.size,
                "count": stat.count,
            }
            for stat in top_stats[:200]  # limit to top 200 allocations
        ]

        with open(heap_path, "w", encoding="utf-8") as fh:
            json.dump(heap_data, fh, indent=2)

        # Diagnostic summary
        total = sum(s.size for s in top_stats)
        diag_data = {
            "timestamp": ts,
            "total_traced_bytes": total,
            "top_allocation_count": len(heap_data),
        }
        with open(diag_path, "w", encoding="utf-8") as fh:
            json.dump(diag_data, fh, indent=2)

        return {
            "success": True,
            "heap_path": heap_path,
            "diag_path": diag_path,
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call() -> Dict[str, str]:
    """
    Trigger a heap dump and return the file paths (or an error message).

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``
    """
    # Try the real service first, fall back to our built-in implementation
    result: Optional[Dict[str, object]] = None
    try:
        from claude_code.utils.heap_dump_service import perform_heap_dump  # type: ignore[import]
        result = await perform_heap_dump()
    except ImportError:
        result = _perform_heap_dump()

    if not result.get("success", False):
        error_msg = result.get("error", "Unknown error")
        return {
            "type": "text",
            "value": f"Failed to create heap dump: {error_msg}",
        }

    heap_path: str = str(result.get("heap_path", ""))
    diag_path: str = str(result.get("diag_path", ""))

    return {
        "type": "text",
        "value": f"{heap_path}\n{diag_path}",
    }
