"""
perfetto_tracing.py — Perfetto/Chrome Trace Event format tracing for Claude Code.

Ported from: utils/telemetry/perfettoTracing.ts

Generates traces in the Chrome Trace Event format viewable at ui.perfetto.dev.
Enable via environment variable CLAUDE_CODE_PERFETTO_TRACE=1 (or a file path).
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Literal, Optional

from typing_extensions import TypedDict, NotRequired

# ---------------------------------------------------------------------------
# Chrome Trace Event format types
# See: https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU
# ---------------------------------------------------------------------------

TraceEventPhase = Literal[
    "B",  # Begin duration event
    "E",  # End duration event
    "X",  # Complete event (with duration)
    "i",  # Instant event
    "C",  # Counter event
    "b",  # Async begin
    "n",  # Async instant
    "e",  # Async end
    "M",  # Metadata event
]


class TraceEvent(TypedDict):
    name: str
    cat: str
    ph: str           # TraceEventPhase
    ts: float         # Timestamp in microseconds
    pid: int          # Process ID
    tid: int          # Thread ID
    dur: NotRequired[float]             # Duration in microseconds (for 'X' events)
    args: NotRequired[Dict[str, Any]]
    id: NotRequired[str]                # For async events
    scope: NotRequired[str]


# ---------------------------------------------------------------------------
# Internal agent-info / pending-span types
# ---------------------------------------------------------------------------

class _AgentInfo(TypedDict):
    agentId: str
    agentName: str
    parentAgentId: NotRequired[Optional[str]]
    processId: int
    threadId: int


class _PendingSpan(TypedDict):
    name: str
    category: str
    startTime: float
    agentInfo: _AgentInfo
    args: Dict[str, Any]


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_is_enabled: bool = False
_trace_path: Optional[str] = None

_metadata_events: List[TraceEvent] = []
_events: List[TraceEvent] = []

MAX_EVENTS = 100_000

_pending_spans: Dict[str, _PendingSpan] = {}
_agent_registry: Dict[str, _AgentInfo] = {}
_total_agent_count: int = 0
_start_time_ms: float = 0.0
_span_id_counter: int = 0
_trace_written: bool = False

_process_id_counter: int = 1
_agent_id_to_process_id: Dict[str, int] = {}

STALE_SPAN_TTL_MS: int = 30 * 60 * 1000  # 30 minutes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _djb2_hash(s: str) -> int:
    """Simple DJB2 hash (mirrors djb2Hash from TS)."""
    h = 5381
    for c in s:
        h = ((h << 5) + h + ord(c)) & 0xFFFFFFFF
    # Convert to signed 32-bit
    if h >= 0x80000000:
        h -= 0x100000000
    return h


def _string_to_numeric_hash(s: str) -> int:
    return abs(_djb2_hash(s)) or 1


def _get_process_id_for_agent(agent_id: str) -> int:
    global _process_id_counter
    existing = _agent_id_to_process_id.get(agent_id)
    if existing is not None:
        return existing
    _process_id_counter += 1
    _agent_id_to_process_id[agent_id] = _process_id_counter
    return _process_id_counter


def _get_timestamp_us() -> float:
    """Current time in microseconds relative to trace start."""
    return (time.time() * 1000 - _start_time_ms) * 1000


def _generate_span_id() -> str:
    global _span_id_counter
    _span_id_counter += 1
    return f"span_{_span_id_counter}"


def _get_current_agent_info() -> _AgentInfo:
    global _total_agent_count
    # Fallback: use process id as agent id, 'main' as name
    agent_id = str(os.getpid())
    agent_name = "main"

    existing = _agent_registry.get(agent_id)
    if existing is not None:
        return existing

    info: _AgentInfo = {
        "agentId": agent_id,
        "agentName": agent_name,
        "processId": 1,
        "threadId": _string_to_numeric_hash(agent_name),
    }
    _agent_registry[agent_id] = info
    _total_agent_count += 1
    return info


def _emit_process_metadata(agent_info: _AgentInfo) -> None:
    if not _is_enabled:
        return

    _metadata_events.append({
        "name": "process_name",
        "cat": "__metadata",
        "ph": "M",
        "ts": 0,
        "pid": agent_info["processId"],
        "tid": 0,
        "args": {"name": agent_info["agentName"]},
    })

    _metadata_events.append({
        "name": "thread_name",
        "cat": "__metadata",
        "ph": "M",
        "ts": 0,
        "pid": agent_info["processId"],
        "tid": agent_info["threadId"],
        "args": {"name": agent_info["agentName"]},
    })

    parent_id = agent_info.get("parentAgentId")
    if parent_id:
        _metadata_events.append({
            "name": "parent_agent",
            "cat": "__metadata",
            "ph": "M",
            "ts": 0,
            "pid": agent_info["processId"],
            "tid": 0,
            "args": {"parent_agent_id": parent_id},
        })


def _evict_oldest_events() -> None:
    global _events
    if len(_events) < MAX_EVENTS:
        return
    dropped = _events[: MAX_EVENTS // 2]
    _events[:] = _events[MAX_EVENTS // 2 :]
    marker: TraceEvent = {
        "name": "trace_truncated",
        "cat": "__metadata",
        "ph": "i",
        "ts": dropped[-1]["ts"] if dropped else 0,
        "pid": 1,
        "tid": 0,
        "args": {"dropped_events": len(dropped)},
    }
    _events.insert(0, marker)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def initialize_perfetto_tracing() -> None:
    """Initialize Perfetto tracing. Call early in the application lifecycle."""
    global _is_enabled, _trace_path, _start_time_ms

    env_value = os.environ.get("CLAUDE_CODE_PERFETTO_TRACE", "")
    if not env_value or env_value.lower() in ("0", "false", "no", "off"):
        return

    _is_enabled = True
    _start_time_ms = time.time() * 1000

    # Determine output path
    truthy_vals = {"1", "true", "yes", "on"}
    if env_value.lower() in truthy_vals:
        home = os.environ.get("HOME", os.path.expanduser("~"))
        traces_dir = os.path.join(home, ".claude", "traces")
        _trace_path = os.path.join(traces_dir, f"trace-python.json")
    else:
        _trace_path = env_value

    # Emit metadata for main agent
    main_agent = _get_current_agent_info()
    _emit_process_metadata(main_agent)


def is_perfetto_tracing_enabled() -> bool:
    """Check whether Perfetto tracing is currently enabled."""
    return _is_enabled


def register_agent(
    agent_id: str,
    agent_name: str,
    parent_agent_id: Optional[str] = None,
) -> None:
    """Register a new agent/subagent in the trace."""
    global _total_agent_count

    if not _is_enabled:
        return

    info: _AgentInfo = {
        "agentId": agent_id,
        "agentName": agent_name,
        "processId": _get_process_id_for_agent(agent_id),
        "threadId": _string_to_numeric_hash(agent_name),
    }
    if parent_agent_id is not None:
        info["parentAgentId"] = parent_agent_id

    _agent_registry[agent_id] = info
    _total_agent_count += 1
    _emit_process_metadata(info)


def unregister_agent(agent_id: str) -> None:
    """Unregister an agent to free memory."""
    if not _is_enabled:
        return
    _agent_registry.pop(agent_id, None)
    _agent_id_to_process_id.pop(agent_id, None)


# ---------------------------------------------------------------------------
# LLM Request spans
# ---------------------------------------------------------------------------

def start_llm_request_perfetto_span(
    model: str,
    prompt_tokens: Optional[int] = None,
    message_id: Optional[str] = None,
    is_speculative: bool = False,
    query_source: Optional[str] = None,
) -> str:
    """Start an API/LLM call span. Returns span ID."""
    if not _is_enabled:
        return ""

    span_id = _generate_span_id()
    agent_info = _get_current_agent_info()
    start_ts = _get_timestamp_us()

    span_args: Dict[str, Any] = {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "message_id": message_id,
        "is_speculative": is_speculative,
        "query_source": query_source,
    }

    _pending_spans[span_id] = {
        "name": "API Call",
        "category": "api",
        "startTime": start_ts,
        "agentInfo": agent_info,
        "args": span_args,
    }

    _events.append({
        "name": "API Call",
        "cat": "api",
        "ph": "B",
        "ts": start_ts,
        "pid": agent_info["processId"],
        "tid": agent_info["threadId"],
        "args": span_args,
    })

    return span_id


def end_llm_request_perfetto_span(
    span_id: str,
    ttft_ms: Optional[float] = None,
    ttlt_ms: Optional[float] = None,
    prompt_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cache_read_tokens: Optional[int] = None,
    cache_creation_tokens: Optional[int] = None,
    message_id: Optional[str] = None,
    success: bool = True,
    error: Optional[str] = None,
    request_setup_ms: Optional[float] = None,
    attempt_start_times: Optional[List[float]] = None,
) -> None:
    """End an LLM request span with response metadata."""
    if not _is_enabled or not span_id:
        return

    pending = _pending_spans.get(span_id)
    if pending is None:
        return

    end_time = _get_timestamp_us()
    duration = end_time - pending["startTime"]

    resolved_prompt_tokens = prompt_tokens or pending["args"].get("prompt_tokens")

    # Derived metrics
    itps: Optional[float] = None
    if ttft_ms and resolved_prompt_tokens and ttft_ms > 0:
        itps = round((resolved_prompt_tokens / (ttft_ms / 1000)) * 100) / 100

    sampling_ms: Optional[float] = None
    if ttlt_ms is not None and ttft_ms is not None:
        sampling_ms = ttlt_ms - ttft_ms

    otps: Optional[float] = None
    if sampling_ms and output_tokens and sampling_ms > 0:
        otps = round((output_tokens / (sampling_ms / 1000)) * 100) / 100

    cache_hit_rate: Optional[float] = None
    if cache_read_tokens is not None and resolved_prompt_tokens and resolved_prompt_tokens > 0:
        cache_hit_rate = round((cache_read_tokens / resolved_prompt_tokens) * 10000) / 100

    setup_us = (request_setup_ms * 1000) if (request_setup_ms and request_setup_ms > 0) else 0.0

    # Request Setup sub-span
    if setup_us > 0:
        setup_end_ts = pending["startTime"] + setup_us
        _events.append({
            "name": "Request Setup",
            "cat": "api,setup",
            "ph": "B",
            "ts": pending["startTime"],
            "pid": pending["agentInfo"]["processId"],
            "tid": pending["agentInfo"]["threadId"],
            "args": {
                "request_setup_ms": request_setup_ms,
                "attempt_count": len(attempt_start_times) if attempt_start_times else 1,
            },
        })

        if attempt_start_times and len(attempt_start_times) > 1:
            base_wall_ms = attempt_start_times[0]
            for i in range(len(attempt_start_times) - 1):
                attempt_start_us = pending["startTime"] + (attempt_start_times[i] - base_wall_ms) * 1000
                attempt_end_us = pending["startTime"] + (attempt_start_times[i + 1] - base_wall_ms) * 1000
                _events.append({
                    "name": f"Attempt {i + 1} (retry)",
                    "cat": "api,retry",
                    "ph": "B",
                    "ts": attempt_start_us,
                    "pid": pending["agentInfo"]["processId"],
                    "tid": pending["agentInfo"]["threadId"],
                    "args": {"attempt": i + 1},
                })
                _events.append({
                    "name": f"Attempt {i + 1} (retry)",
                    "cat": "api,retry",
                    "ph": "E",
                    "ts": attempt_end_us,
                    "pid": pending["agentInfo"]["processId"],
                    "tid": pending["agentInfo"]["threadId"],
                })

        _events.append({
            "name": "Request Setup",
            "cat": "api,setup",
            "ph": "E",
            "ts": setup_end_ts,
            "pid": pending["agentInfo"]["processId"],
            "tid": pending["agentInfo"]["threadId"],
        })

    # First Token / Sampling sub-spans
    if ttft_ms is not None:
        first_token_start_ts = pending["startTime"] + setup_us
        first_token_end_ts = first_token_start_ts + ttft_ms * 1000

        _events.append({
            "name": "First Token",
            "cat": "api,ttft",
            "ph": "B",
            "ts": first_token_start_ts,
            "pid": pending["agentInfo"]["processId"],
            "tid": pending["agentInfo"]["threadId"],
            "args": {
                "ttft_ms": ttft_ms,
                "prompt_tokens": resolved_prompt_tokens,
                "itps": itps,
                "cache_hit_rate_pct": cache_hit_rate,
            },
        })
        _events.append({
            "name": "First Token",
            "cat": "api,ttft",
            "ph": "E",
            "ts": first_token_end_ts,
            "pid": pending["agentInfo"]["processId"],
            "tid": pending["agentInfo"]["threadId"],
        })

        if ttlt_ms is not None:
            actual_sampling_ms = ttlt_ms - ttft_ms - setup_us / 1000
            if actual_sampling_ms > 0:
                _events.append({
                    "name": "Sampling",
                    "cat": "api,sampling",
                    "ph": "B",
                    "ts": first_token_end_ts,
                    "pid": pending["agentInfo"]["processId"],
                    "tid": pending["agentInfo"]["threadId"],
                    "args": {
                        "sampling_ms": actual_sampling_ms,
                        "output_tokens": output_tokens,
                        "otps": otps,
                    },
                })
                _events.append({
                    "name": "Sampling",
                    "cat": "api,sampling",
                    "ph": "E",
                    "ts": first_token_end_ts + actual_sampling_ms * 1000,
                    "pid": pending["agentInfo"]["processId"],
                    "tid": pending["agentInfo"]["threadId"],
                })

    # Final args merged
    final_args: Dict[str, Any] = {
        **pending["args"],
        "ttft_ms": ttft_ms,
        "ttlt_ms": ttlt_ms,
        "prompt_tokens": resolved_prompt_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "message_id": message_id or pending["args"].get("message_id"),
        "success": success,
        "error": error,
        "duration_ms": duration / 1000,
        "request_setup_ms": request_setup_ms,
        "itps": itps,
        "otps": otps,
        "cache_hit_rate_pct": cache_hit_rate,
    }

    _events.append({
        "name": pending["name"],
        "cat": pending["category"],
        "ph": "E",
        "ts": end_time,
        "pid": pending["agentInfo"]["processId"],
        "tid": pending["agentInfo"]["threadId"],
        "args": final_args,
    })

    del _pending_spans[span_id]


# ---------------------------------------------------------------------------
# Tool spans
# ---------------------------------------------------------------------------

def start_tool_perfetto_span(
    tool_name: str,
    tool_use_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    extra_args: Optional[Dict[str, Any]] = None,
) -> str:
    """Start a tool execution span. Returns span ID."""
    if not _is_enabled:
        return ""

    span_id = _generate_span_id()
    agent_info = _get_current_agent_info()
    start_ts = _get_timestamp_us()

    span_args: Dict[str, Any] = {"tool_name": tool_name}
    if tool_use_id:
        span_args["tool_use_id"] = tool_use_id
    if agent_id:
        span_args["agent_id"] = agent_id
    if extra_args:
        span_args.update(extra_args)

    _pending_spans[span_id] = {
        "name": f"Tool: {tool_name}",
        "category": "tool",
        "startTime": start_ts,
        "agentInfo": agent_info,
        "args": span_args,
    }

    _events.append({
        "name": f"Tool: {tool_name}",
        "cat": "tool",
        "ph": "B",
        "ts": start_ts,
        "pid": agent_info["processId"],
        "tid": agent_info["threadId"],
        "args": span_args,
    })

    return span_id


def end_tool_perfetto_span(
    span_id: str,
    success: bool = True,
    error: Optional[str] = None,
    result_tokens: Optional[int] = None,
) -> None:
    """End a tool execution span."""
    if not _is_enabled or not span_id:
        return

    pending = _pending_spans.get(span_id)
    if pending is None:
        return

    end_time = _get_timestamp_us()
    duration = end_time - pending["startTime"]

    _events.append({
        "name": pending["name"],
        "cat": pending["category"],
        "ph": "E",
        "ts": end_time,
        "pid": pending["agentInfo"]["processId"],
        "tid": pending["agentInfo"]["threadId"],
        "args": {
            **pending["args"],
            "success": success,
            "error": error,
            "result_tokens": result_tokens,
            "duration_ms": duration / 1000,
        },
    })

    del _pending_spans[span_id]


# ---------------------------------------------------------------------------
# User input spans
# ---------------------------------------------------------------------------

def start_user_input_perfetto_span(context: Optional[str] = None) -> str:
    """Start a 'waiting for user input' span. Returns span ID."""
    if not _is_enabled:
        return ""

    span_id = _generate_span_id()
    agent_info = _get_current_agent_info()
    start_ts = _get_timestamp_us()

    _pending_spans[span_id] = {
        "name": "Waiting for User Input",
        "category": "user_input",
        "startTime": start_ts,
        "agentInfo": agent_info,
        "args": {"context": context},
    }

    _events.append({
        "name": "Waiting for User Input",
        "cat": "user_input",
        "ph": "B",
        "ts": start_ts,
        "pid": agent_info["processId"],
        "tid": agent_info["threadId"],
        "args": {"context": context},
    })

    return span_id


def end_user_input_perfetto_span(
    span_id: str,
    decision: Optional[str] = None,
    source: Optional[str] = None,
) -> None:
    """End a user input span."""
    if not _is_enabled or not span_id:
        return

    pending = _pending_spans.get(span_id)
    if pending is None:
        return

    end_time = _get_timestamp_us()
    duration = end_time - pending["startTime"]

    _events.append({
        "name": pending["name"],
        "cat": pending["category"],
        "ph": "E",
        "ts": end_time,
        "pid": pending["agentInfo"]["processId"],
        "tid": pending["agentInfo"]["threadId"],
        "args": {
            **pending["args"],
            "decision": decision,
            "source": source,
            "duration_ms": duration / 1000,
        },
    })

    del _pending_spans[span_id]


# ---------------------------------------------------------------------------
# Instant / counter events
# ---------------------------------------------------------------------------

def emit_perfetto_instant(
    name: str,
    category: str = "instant",
    args: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit an instant (marker) event."""
    if not _is_enabled:
        return

    agent_info = _get_current_agent_info()
    event: TraceEvent = {
        "name": name,
        "cat": category,
        "ph": "i",
        "ts": _get_timestamp_us(),
        "pid": agent_info["processId"],
        "tid": agent_info["threadId"],
    }
    if args is not None:
        event["args"] = args
    _events.append(event)


def emit_perfetto_counter(
    name: str,
    values: Dict[str, float],
) -> None:
    """Emit a counter event for tracking metrics over time."""
    if not _is_enabled:
        return

    agent_info = _get_current_agent_info()
    _events.append({
        "name": name,
        "cat": "counter",
        "ph": "C",
        "ts": _get_timestamp_us(),
        "pid": agent_info["processId"],
        "tid": agent_info["threadId"],
        "args": values,  # type: ignore[arg-type]
    })


# ---------------------------------------------------------------------------
# Interaction spans
# ---------------------------------------------------------------------------

def start_interaction_perfetto_span(user_prompt: Optional[str] = None) -> str:
    """Start an interaction span wrapping a full user request cycle."""
    if not _is_enabled:
        return ""

    span_id = _generate_span_id()
    agent_info = _get_current_agent_info()
    start_ts = _get_timestamp_us()

    span_args: Dict[str, Any] = {
        "user_prompt_length": len(user_prompt) if user_prompt else None,
    }

    _pending_spans[span_id] = {
        "name": "Interaction",
        "category": "interaction",
        "startTime": start_ts,
        "agentInfo": agent_info,
        "args": span_args,
    }

    _events.append({
        "name": "Interaction",
        "cat": "interaction",
        "ph": "B",
        "ts": start_ts,
        "pid": agent_info["processId"],
        "tid": agent_info["threadId"],
        "args": span_args,
    })

    return span_id


def end_interaction_perfetto_span(span_id: str) -> None:
    """End an interaction span."""
    if not _is_enabled or not span_id:
        return

    pending = _pending_spans.get(span_id)
    if pending is None:
        return

    end_time = _get_timestamp_us()
    duration = end_time - pending["startTime"]

    _events.append({
        "name": pending["name"],
        "cat": pending["category"],
        "ph": "E",
        "ts": end_time,
        "pid": pending["agentInfo"]["processId"],
        "tid": pending["agentInfo"]["threadId"],
        "args": {
            **pending["args"],
            "duration_ms": duration / 1000,
        },
    })

    del _pending_spans[span_id]


# ---------------------------------------------------------------------------
# Query / reset helpers
# ---------------------------------------------------------------------------

def get_perfetto_events() -> List[TraceEvent]:
    """Return all recorded events (metadata + regular)."""
    return list(_metadata_events) + list(_events)


def reset_perfetto_tracer() -> None:
    """Reset all tracer state — primarily for testing."""
    global _is_enabled, _trace_path, _start_time_ms, _span_id_counter
    global _total_agent_count, _process_id_counter, _trace_written

    _metadata_events.clear()
    _events.clear()
    _pending_spans.clear()
    _agent_registry.clear()
    _agent_id_to_process_id.clear()

    _is_enabled = False
    _trace_path = None
    _start_time_ms = 0.0
    _span_id_counter = 0
    _total_agent_count = 0
    _process_id_counter = 1
    _trace_written = False


def write_perfetto_trace(output_path: Optional[str] = None) -> bool:
    """Write the current trace to disk (sync). Returns True on success."""
    global _trace_written

    path = output_path or _trace_path
    if not _is_enabled or not path:
        return False

    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        doc = {
            "traceEvents": [dict(e) for e in get_perfetto_events()],
            "metadata": {
                "trace_start_time_ms": _start_time_ms,
                "agent_count": _total_agent_count,
                "total_event_count": len(_metadata_events) + len(_events),
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        _trace_written = True
        return True
    except OSError:
        return False
