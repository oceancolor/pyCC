"""
Session state management – tracks whether the session is idle, running,
or blocked on a required action.
Ported from sessionState.ts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

SessionStatus = Literal["idle", "running", "requires_action"]


@dataclass
class RequiresActionDetails:
    tool_name: str
    action_description: str
    tool_use_id: str
    request_id: str
    input: Optional[dict[str, Any]] = None


@dataclass
class SessionExternalMetadata:
    permission_mode: Optional[str] = None
    is_ultraplan_mode: Optional[bool] = None
    model: Optional[str] = None
    pending_action: Optional[RequiresActionDetails] = None
    post_turn_summary: Optional[Any] = None
    task_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Session state dataclass (for local in-process use)
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    """In-process session flags.  Extended from the TS global state shape."""
    status: SessionStatus = "idle"
    is_plan_mode: bool = False
    is_verbose: bool = False
    thinking_enabled: bool = True
    pending_action: Optional[RequiresActionDetails] = None
    model: Optional[str] = None
    permission_mode: Optional[str] = None


# ---------------------------------------------------------------------------
# Module-level singleton (mirrors TS globals)
# ---------------------------------------------------------------------------

_current_status: SessionStatus = "idle"
_has_pending_action: bool = False

StateChangedListener = Callable[[SessionStatus, Optional[RequiresActionDetails]], None]
MetadataChangedListener = Callable[[SessionExternalMetadata], None]
PermissionModeChangedListener = Callable[[str], None]

_state_listener: Optional[StateChangedListener] = None
_metadata_listener: Optional[MetadataChangedListener] = None
_permission_mode_listener: Optional[PermissionModeChangedListener] = None


def set_session_state_changed_listener(
    cb: Optional[StateChangedListener],
) -> None:
    global _state_listener
    _state_listener = cb


def set_session_metadata_changed_listener(
    cb: Optional[MetadataChangedListener],
) -> None:
    global _metadata_listener
    _metadata_listener = cb


def set_permission_mode_changed_listener(
    cb: Optional[PermissionModeChangedListener],
) -> None:
    global _permission_mode_listener
    _permission_mode_listener = cb


def get_session_state() -> SessionStatus:
    """Return the current module-level session status."""
    return _current_status


def notify_session_state_changed(
    state: SessionStatus,
    details: Optional[RequiresActionDetails] = None,
) -> None:
    """Update the current session state and fire registered listeners."""
    global _current_status, _has_pending_action

    _current_status = state

    if _state_listener:
        _state_listener(state, details)

    if state == "requires_action" and details is not None:
        _has_pending_action = True
        if _metadata_listener:
            _metadata_listener(SessionExternalMetadata(pending_action=details))
    elif _has_pending_action:
        _has_pending_action = False
        if _metadata_listener:
            _metadata_listener(SessionExternalMetadata(pending_action=None))

    # Clear task_summary when returning to idle
    if state == "idle" and _metadata_listener:
        _metadata_listener(SessionExternalMetadata(task_summary=None))

    # Optionally emit SDK event (controlled by env var)
    if os.environ.get("CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS", "").lower() in (
        "1", "true", "yes"
    ):
        _emit_sdk_event(state)


def notify_session_metadata_changed(metadata: SessionExternalMetadata) -> None:
    """Fire the metadata listener with the given metadata."""
    if _metadata_listener:
        _metadata_listener(metadata)


def notify_permission_mode_changed(mode: str) -> None:
    """Fire the permission-mode listener with the new mode."""
    if _permission_mode_listener:
        _permission_mode_listener(mode)


def update_session_state(
    *,
    is_plan_mode: Optional[bool] = None,
    is_verbose: Optional[bool] = None,
    thinking_enabled: Optional[bool] = None,
    model: Optional[str] = None,
    permission_mode: Optional[str] = None,
) -> None:
    """
    Convenience helper to update specific fields on the module-level state.

    This does NOT change the session status; use notify_session_state_changed for that.
    The metadata listener is fired with changed fields.
    """
    meta = SessionExternalMetadata()
    if model is not None:
        meta.model = model
    if permission_mode is not None:
        meta.permission_mode = permission_mode
    if is_plan_mode is not None:
        meta.is_ultraplan_mode = is_plan_mode
    notify_session_metadata_changed(meta)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _emit_sdk_event(state: SessionStatus) -> None:
    """Stub: emit a session state event to the SDK event queue."""
    # Full implementation wires into the SDK event queue
    pass
