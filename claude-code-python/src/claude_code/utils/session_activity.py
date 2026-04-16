"""
Session activity tracking with refcount-based heartbeat timer.

The transport registers a keep-alive callback via register_session_activity_callback().
Callers bracket active work with start_session_activity() / stop_session_activity().
While the refcount is > 0 a periodic timer fires every 30 s.

Gated by CLAUDE_CODE_REMOTE_SEND_KEEPALIVES; diagnostic logging always fires.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

SESSION_ACTIVITY_INTERVAL_S: float = 30.0

SessionActivityReason = Literal["api_call", "tool_exec"]


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_activity_callback: Optional[Callable[[], None]] = None
_refcount: int = 0
_active_reasons: dict[str, int] = {}
_oldest_activity_started_at: Optional[float] = None
_heartbeat_timer: Optional[threading.Timer] = None
_idle_timer: Optional[threading.Timer] = None
_lock = threading.Lock()


def _is_keepalives_enabled() -> bool:
    val = os.environ.get("CLAUDE_CODE_REMOTE_SEND_KEEPALIVES", "")
    return val.lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Timer helpers
# ---------------------------------------------------------------------------

def _fire_heartbeat() -> None:
    """Periodic heartbeat callback; reschedules itself."""
    global _heartbeat_timer
    if _is_keepalives_enabled() and _activity_callback:
        _activity_callback()
    with _lock:
        if _refcount > 0:
            _heartbeat_timer = threading.Timer(SESSION_ACTIVITY_INTERVAL_S, _fire_heartbeat)
            _heartbeat_timer.daemon = True
            _heartbeat_timer.start()


def _start_heartbeat_timer() -> None:
    global _heartbeat_timer
    _clear_idle_timer()
    _heartbeat_timer = threading.Timer(SESSION_ACTIVITY_INTERVAL_S, _fire_heartbeat)
    _heartbeat_timer.daemon = True
    _heartbeat_timer.start()


def _fire_idle() -> None:
    global _idle_timer
    _idle_timer = None


def _start_idle_timer() -> None:
    global _idle_timer
    _clear_idle_timer()
    if _activity_callback is None:
        return
    _idle_timer = threading.Timer(SESSION_ACTIVITY_INTERVAL_S, _fire_idle)
    _idle_timer.daemon = True
    _idle_timer.start()


def _clear_idle_timer() -> None:
    global _idle_timer
    if _idle_timer is not None:
        _idle_timer.cancel()
        _idle_timer = None


def _stop_heartbeat_timer() -> None:
    global _heartbeat_timer
    if _heartbeat_timer is not None:
        _heartbeat_timer.cancel()
        _heartbeat_timer = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_session_activity_callback(cb: Callable[[], None]) -> None:
    """Register the keep-alive callback. Restarts timer if work is in progress."""
    global _activity_callback
    with _lock:
        _activity_callback = cb
        if _refcount > 0 and _heartbeat_timer is None:
            _start_heartbeat_timer()


def unregister_session_activity_callback() -> None:
    """Unregister the keep-alive callback and stop timers."""
    global _activity_callback
    with _lock:
        _activity_callback = None
        _stop_heartbeat_timer()
        _clear_idle_timer()


def send_session_activity_signal() -> None:
    """Fire the activity callback once (used for immediate keepalive)."""
    if _is_keepalives_enabled() and _activity_callback:
        _activity_callback()


def is_session_activity_tracking_active() -> bool:
    return _activity_callback is not None


def start_session_activity(reason: SessionActivityReason) -> None:
    """Increment refcount. Starts heartbeat timer on 0→1 transition."""
    global _refcount, _oldest_activity_started_at
    with _lock:
        _refcount += 1
        _active_reasons[reason] = _active_reasons.get(reason, 0) + 1
        if _refcount == 1:
            _oldest_activity_started_at = time.monotonic()
            if _activity_callback is not None and _heartbeat_timer is None:
                _start_heartbeat_timer()


def stop_session_activity(reason: SessionActivityReason) -> None:
    """Decrement refcount. Stops heartbeat and starts idle timer on →0 transition."""
    global _refcount
    with _lock:
        if _refcount > 0:
            _refcount -= 1
        n = _active_reasons.get(reason, 0) - 1
        if n > 0:
            _active_reasons[reason] = n
        else:
            _active_reasons.pop(reason, None)
        if _refcount == 0 and _heartbeat_timer is not None:
            _stop_heartbeat_timer()
            _start_idle_timer()


def get_refcount() -> int:
    return _refcount


def get_active_reasons() -> dict[str, int]:
    return dict(_active_reasons)


def reset() -> None:
    """Reset all state (for testing)."""
    global _refcount, _oldest_activity_started_at, _activity_callback
    with _lock:
        _stop_heartbeat_timer()
        _clear_idle_timer()
        _refcount = 0
        _active_reasons.clear()
        _oldest_activity_started_at = None
        _activity_callback = None
