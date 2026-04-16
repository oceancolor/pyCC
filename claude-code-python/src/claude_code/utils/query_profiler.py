"""
query_profiler.py
记录每次 LLM query 的性能数据（耗时、checkpoints、阶段分析）。
移植自 queryProfiler.ts
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Environment flag
# ---------------------------------------------------------------------------

_ENABLED: bool = os.environ.get("CLAUDE_CODE_PROFILE_QUERY", "").strip() in (
    "1", "true", "yes", "on",
)

# ---------------------------------------------------------------------------
# Module-level state (mirrors TS module-level vars)
# ---------------------------------------------------------------------------

_checkpoints: list[tuple[str, float]] = []   # (name, time_s)
_query_count: int = 0
_first_token_time: Optional[float] = None    # relative seconds from baseline


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_query_profile() -> None:
    """Start profiling a new query session (clears previous state)."""
    global _checkpoints, _query_count, _first_token_time
    if not _ENABLED:
        return
    _checkpoints = []
    _first_token_time = None
    _query_count += 1
    query_checkpoint("query_user_input_received")


def query_checkpoint(name: str) -> None:
    """Record a named checkpoint at the current time."""
    if not _ENABLED:
        return
    _checkpoints.append((name, time.perf_counter()))

    global _first_token_time
    if name == "query_first_chunk_received" and _first_token_time is None:
        if len(_checkpoints) >= 2:
            baseline = _checkpoints[0][1]
            _first_token_time = _checkpoints[-1][1] - baseline


def end_query_profile() -> None:
    """Mark the end of the current query profiling session."""
    if not _ENABLED:
        return
    query_checkpoint("query_profile_end")


def get_query_profile_report() -> str:
    """Return a formatted text report of all recorded checkpoints."""
    if not _ENABLED:
        return "Query profiling not enabled (set CLAUDE_CODE_PROFILE_QUERY=1)"
    if not _checkpoints:
        return "No query profiling checkpoints recorded"

    lines: list[str] = []
    lines.append("=" * 80)
    lines.append(f"QUERY PROFILING REPORT - Query #{_query_count}")
    lines.append("=" * 80)
    lines.append("")

    baseline = _checkpoints[0][1]
    prev_time = baseline
    api_request_ms: float = 0.0
    first_chunk_ms: float = 0.0

    for name, ts in _checkpoints:
        rel_ms = (ts - baseline) * 1000
        delta_ms = (ts - prev_time) * 1000
        warning = _slow_warning(delta_ms, name)
        lines.append(f"  {rel_ms:10.1f}ms  (+{delta_ms:8.1f}ms)  {name}{warning}")
        if name == "query_api_request_sent":
            api_request_ms = rel_ms
        if name == "query_first_chunk_received":
            first_chunk_ms = rel_ms
        prev_time = ts

    lines.append("")
    lines.append("-" * 80)

    if first_chunk_ms > 0:
        pre_req = api_request_ms
        net_lat = first_chunk_ms - api_request_ms
        pre_pct = (pre_req / first_chunk_ms * 100) if first_chunk_ms else 0
        net_pct = (net_lat / first_chunk_ms * 100) if first_chunk_ms else 0
        lines.append(f"Total TTFT: {first_chunk_ms:.1f}ms")
        lines.append(f"  - Pre-request overhead: {pre_req:.1f}ms ({pre_pct:.1f}%)")
        lines.append(f"  - Network latency: {net_lat:.1f}ms ({net_pct:.1f}%)")
    else:
        last_ts = _checkpoints[-1][1] if _checkpoints else baseline
        total_ms = (last_ts - baseline) * 1000
        lines.append(f"Total time: {total_ms:.1f}ms")

    lines.append(_phase_summary())
    lines.append("=" * 80)
    return "\n".join(lines)


def log_query_profile_report() -> None:
    """Print the profile report to stdout (mirrors logForDebugging in TS)."""
    if not _ENABLED:
        return
    print(get_query_profile_report())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SLOW_THRESHOLD_MS = 100
_VERY_SLOW_THRESHOLD_MS = 1000


def _slow_warning(delta_ms: float, name: str) -> str:
    if name == "query_user_input_received":
        return ""
    if delta_ms > _VERY_SLOW_THRESHOLD_MS:
        return "  ⚠️  VERY SLOW"
    if delta_ms > _SLOW_THRESHOLD_MS:
        return "  ⚠️  SLOW"
    if "git_status" in name and delta_ms > 50:
        return "  ⚠️  git status"
    if "tool_schema" in name and delta_ms > 50:
        return "  ⚠️  tool schemas"
    if "client_creation" in name and delta_ms > 50:
        return "  ⚠️  client creation"
    return ""


_PHASES = [
    ("Context loading",       "query_context_loading_start",        "query_context_loading_end"),
    ("Microcompact",          "query_microcompact_start",           "query_microcompact_end"),
    ("Autocompact",           "query_autocompact_start",            "query_autocompact_end"),
    ("Query setup",           "query_setup_start",                  "query_setup_end"),
    ("Tool schemas",          "query_tool_schema_build_start",      "query_tool_schema_build_end"),
    ("Msg normalization",     "query_message_normalization_start",  "query_message_normalization_end"),
    ("Client creation",       "query_client_creation_start",        "query_client_creation_end"),
    ("Network TTFB",          "query_api_request_sent",             "query_first_chunk_received"),
    ("Tool execution",        "query_tool_execution_start",         "query_tool_execution_end"),
]


def _phase_summary() -> str:
    if not _checkpoints:
        return ""
    baseline = _checkpoints[0][1]
    mark_map: dict[str, float] = {
        name: (ts - baseline) * 1000 for name, ts in _checkpoints
    }

    lines = ["", "PHASE BREAKDOWN:"]
    for label, start_key, end_key in _PHASES:
        start_ms = mark_map.get(start_key)
        end_ms = mark_map.get(end_key)
        if start_ms is not None and end_ms is not None:
            duration = end_ms - start_ms
            bar = "█" * min(int(duration / 10) + 1, 50)
            lines.append(f"  {label:<22} {duration:10.1f}ms {bar}")

    api_sent = mark_map.get("query_api_request_sent")
    if api_sent is not None:
        lines.append("")
        lines.append(f"  {'Total pre-API overhead':<22} {api_sent:10.1f}ms")

    return "\n".join(lines)
