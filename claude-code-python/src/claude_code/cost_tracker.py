"""
Cost tracking and session cost persistence.
Ported from cost-tracker.ts (323 lines → core).
"""
from __future__ import annotations
import os
import json
import time
from typing import Any, Dict, Optional

# In-memory cost state
_state: Dict[str, Any] = {
    "total_cost_usd": 0.0,
    "total_api_duration": 0,
    "total_tool_duration": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cache_read_tokens": 0,
    "total_cache_creation_tokens": 0,
    "total_lines_added": 0,
    "total_lines_removed": 0,
    "total_web_search_requests": 0,
    "model_usage": {},
    "has_unknown_model_cost": False,
    "session_start": time.time(),
}


def get_total_cost_usd() -> float:
    return _state["total_cost_usd"]


get_total_cost = get_total_cost_usd  # alias


def get_total_input_tokens() -> int:
    return _state["total_input_tokens"]


def get_total_output_tokens() -> int:
    return _state["total_output_tokens"]


def get_total_cache_read_input_tokens() -> int:
    return _state["total_cache_read_tokens"]


def get_total_cache_creation_input_tokens() -> int:
    return _state["total_cache_creation_tokens"]


def get_total_web_search_requests() -> int:
    return _state["total_web_search_requests"]


def get_total_duration() -> float:
    return time.time() - _state["session_start"]


def get_total_api_duration() -> int:
    return _state["total_api_duration"]


def get_total_api_duration_without_retries() -> int:
    return _state["total_api_duration"]


def get_model_usage() -> dict:
    return dict(_state["model_usage"])


def has_unknown_model_cost() -> bool:
    return _state["has_unknown_model_cost"]


def set_has_unknown_model_cost(val: bool) -> None:
    _state["has_unknown_model_cost"] = val


def get_total_lines_added() -> int:
    return _state["total_lines_added"]


def get_total_lines_removed() -> int:
    return _state["total_lines_removed"]


def add_to_total_lines_changed(added: int, removed: int) -> None:
    _state["total_lines_added"] += added
    _state["total_lines_removed"] += removed


def add_to_total_session_cost(cost_usd: float) -> None:
    _state["total_cost_usd"] += cost_usd


def add_usage(usage: dict, model: str = "", cost_usd: float = 0.0) -> None:
    """Add API usage metrics to running totals."""
    _state["total_input_tokens"] += usage.get("input_tokens", 0)
    _state["total_output_tokens"] += usage.get("output_tokens", 0)
    _state["total_cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
    _state["total_cache_creation_tokens"] += usage.get("cache_creation_input_tokens", 0)
    _state["total_web_search_requests"] += (
        usage.get("server_tool_use", {}).get("web_search_requests", 0)
    )
    _state["total_cost_usd"] += cost_usd
    if model:
        mu = _state["model_usage"].setdefault(model, {
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "invocations": 0
        })
        mu["input_tokens"] += usage.get("input_tokens", 0)
        mu["output_tokens"] += usage.get("output_tokens", 0)
        mu["cost_usd"] += cost_usd
        mu["invocations"] += 1


def format_cost(cost: float) -> str:
    if cost < 0.01:
        return f"<$0.01"
    return f"${cost:.2f}"


def format_total_cost() -> str:
    cost = get_total_cost_usd()
    in_tok = get_total_input_tokens()
    out_tok = get_total_output_tokens()
    duration = get_total_duration()
    return (
        f"Total cost: {format_cost(cost)} | "
        f"Tokens: {in_tok:,} in / {out_tok:,} out | "
        f"Duration: {duration:.1f}s"
    )


def reset_cost_state() -> None:
    global _state
    _state = {
        "total_cost_usd": 0.0,
        "total_api_duration": 0,
        "total_tool_duration": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_creation_tokens": 0,
        "total_lines_added": 0,
        "total_lines_removed": 0,
        "total_web_search_requests": 0,
        "model_usage": {},
        "has_unknown_model_cost": False,
        "session_start": time.time(),
    }


reset_state_for_tests = reset_cost_state


def save_current_session_costs(fps_metrics: Any = None) -> None:
    """Persist current session cost state to disk."""
    session_dir = os.path.join(os.path.expanduser("~"), ".claude", "sessions")
    os.makedirs(session_dir, exist_ok=True)
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "unknown")
    path = os.path.join(session_dir, f"costs-{session_id}.json")
    data = {
        "total_cost_usd": get_total_cost_usd(),
        "total_input_tokens": get_total_input_tokens(),
        "total_output_tokens": get_total_output_tokens(),
        "model_usage": get_model_usage(),
        "saved_at": time.time(),
    }
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


def get_stored_session_costs(session_id: str) -> Optional[dict]:
    session_dir = os.path.join(os.path.expanduser("~"), ".claude", "sessions")
    path = os.path.join(session_dir, f"costs-{session_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None
