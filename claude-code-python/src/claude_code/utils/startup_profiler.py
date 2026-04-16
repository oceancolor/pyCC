# 原始 TS: utils/startupProfiler.ts
"""启动性能分析（记录各阶段耗时）"""
from __future__ import annotations
import time
from typing import Dict, List, Tuple

_checkpoints: List[Tuple[str, float]] = []
_start = time.monotonic()


def profile_checkpoint(name: str) -> None:
    _checkpoints.append((name, time.monotonic() - _start))


def get_profile_report() -> str:
    if not _checkpoints:
        return "(no checkpoints)"
    lines = ["Startup profile:"]
    prev = 0.0
    for name, ts in _checkpoints:
        delta = ts - prev
        lines.append(f"  {name:<30} {ts*1000:6.1f}ms  (+{delta*1000:.1f}ms)")
        prev = ts
    total = _checkpoints[-1][1] if _checkpoints else 0
    lines.append(f"  {'TOTAL':<30} {total*1000:.1f}ms")
    return "\n".join(lines)


def reset_profile() -> None:
    global _start
    _checkpoints.clear()
    _start = time.monotonic()
