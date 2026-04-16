"""
Headless mode profiling utility for measuring per-turn latency in print (-p) mode.

Tracks key timing phases per turn:
- Time to system message output (turn 0 only)
- Time to first query started
- Time to first API response (TTFT)
"""

import os
import random
import time
from typing import Optional

# Detailed profiling mode
_DETAILED_PROFILING: bool = os.environ.get("CLAUDE_CODE_PROFILE_STARTUP", "").lower() in (
    "1", "true", "yes",
)

# Sampling: 100% ant users, 5% external
_STATSIG_LOGGING_SAMPLED: bool = (
    os.environ.get("USER_TYPE") == "ant" or random.random() < 0.05
)

# Enable profiling if either detailed or sampled
_SHOULD_PROFILE: bool = _DETAILED_PROFILING or _STATSIG_LOGGING_SAMPLED

# Current turn number
_current_turn_number: int = -1

# Mark store: name → timestamp (monotonic seconds)
_marks: dict[str, float] = {}


def _is_non_interactive() -> bool:
    """Stub: returns True when running in headless/non-interactive mode."""
    from claude_code.utils.env_utils import is_env_truthy  # lazy import
    return is_env_truthy(os.environ.get("CLAUDE_CODE_NON_INTERACTIVE", ""))


def _clear_marks() -> None:
    _marks.clear()


def headless_profiler_start_turn() -> None:
    """Start a new profiling turn. Clears previous marks, increments turn number."""
    global _current_turn_number
    if not _SHOULD_PROFILE:
        return
    _current_turn_number += 1
    _clear_marks()
    _marks["turn_start"] = time.monotonic() * 1000  # ms
    if _DETAILED_PROFILING:
        print(f"[headlessProfiler] Started turn {_current_turn_number}", flush=True)


def headless_profiler_checkpoint(name: str) -> None:
    """Record a named checkpoint."""
    if not _SHOULD_PROFILE:
        return
    _marks[name] = time.monotonic() * 1000  # ms
    if _DETAILED_PROFILING:
        print(
            f"[headlessProfiler] Checkpoint: {name} at {_marks[name]:.1f}ms",
            flush=True,
        )


def log_headless_profiler_turn() -> None:
    """Compute and log latency metrics for the current turn."""
    if not _SHOULD_PROFILE:
        return
    if not _marks:
        return

    turn_start = _marks.get("turn_start")
    if turn_start is None:
        return

    metadata: dict = {"turn_number": _current_turn_number}

    sys_msg_time = _marks.get("system_message_yielded")
    if sys_msg_time is not None and _current_turn_number == 0:
        metadata["time_to_system_message_ms"] = round(sys_msg_time)

    query_start = _marks.get("query_started")
    if query_start is not None:
        metadata["time_to_query_start_ms"] = round(query_start - turn_start)

    first_chunk = _marks.get("first_chunk")
    if first_chunk is not None:
        metadata["time_to_first_response_ms"] = round(first_chunk - turn_start)

    api_req = _marks.get("api_request_sent")
    if query_start is not None and api_req is not None:
        metadata["query_overhead_ms"] = round(api_req - query_start)

    metadata["checkpoint_count"] = len(_marks)

    entrypoint = os.environ.get("CLAUDE_CODE_ENTRYPOINT")
    if entrypoint:
        metadata["entrypoint"] = entrypoint

    if _DETAILED_PROFILING:
        import json
        print(
            f"[headlessProfiler] Turn {_current_turn_number} metrics: "
            f"{json.dumps(metadata)}",
            flush=True,
        )


def get_current_turn_number() -> int:
    """Return the current turn number."""
    return _current_turn_number


def reset() -> None:
    """Reset all profiling state (for testing)."""
    global _current_turn_number
    _current_turn_number = -1
    _marks.clear()
