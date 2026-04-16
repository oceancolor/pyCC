"""
Profiler base: shared infrastructure for startup/query/headless profilers.
Ported from profilerBase.ts
"""
from __future__ import annotations
import time
from typing import Optional


def get_performance_ms() -> float:
    """Return high-resolution time in milliseconds."""
    return time.perf_counter() * 1000


def format_ms(ms: float) -> str:
    return f"{ms:.3f}"


def format_file_size(bytes_val: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_val < 1024:
            return f"{bytes_val:.1f}{unit}"
        bytes_val //= 1024
    return f"{bytes_val:.1f}TB"


def format_timeline_line(total_ms: float, delta_ms: float, name: str,
                          memory: Optional[dict] = None,
                          total_pad: int = 8, delta_pad: int = 7,
                          extra: str = "") -> str:
    mem_info = ""
    if memory:
        mem_info = f" | RSS: {format_file_size(memory.get('rss', 0))}, Heap: {format_file_size(memory.get('heap_used', 0))}"
    return (f"[+{format_ms(total_ms).rjust(total_pad)}ms] "
            f"(+{format_ms(delta_ms).rjust(delta_pad)}ms) {name}{extra}{mem_info}")
