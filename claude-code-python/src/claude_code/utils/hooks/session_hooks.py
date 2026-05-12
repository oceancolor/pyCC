"""
Session hooks - session-scoped in-memory hooks for per-session hook management.
"""

from __future__ import annotations

import time
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Map,
    Optional,
    Union,
)

if TYPE_CHECKING:
    pass

# HookCommand and related types (simplified Python representations)
HookEvent = str  # e.g. 'PreToolUse', 'Stop', etc.

OnHookSuccess = Callable[["HookCommand | FunctionHook", Any], None]
FunctionHookCallback = Callable[[List[Any], Optional[Any]], Union[bool, "Coroutine"]]


class FunctionHook:
    """Function hook type with callback embedded. Session-scoped only."""

    def __init__(
        self,
        callback: FunctionHookCallback,
        error_message: str,
        hook_id: Optional[str] = None,
        timeout: int = 5000,
        status_message: Optional[str] = None,
    ) -> None:
        self.type = "function"
        self.id = hook_id
        self.timeout = timeout
        self.callback = callback
        self.error_message = error_message
        self.status_message = status_message


# HookCommand is just a dict with a 'type' key for now
HookCommand = Dict[str, Any]


class SessionHookMatcher:
    def __init__(
        self,
        matcher: str,
        hooks: List[Dict[str, Any]],
        skill_root: Optional[str] = None,
    ) -> None:
        self.matcher = matcher
        self.skill_root = skill_root
        self.hooks = hooks  # list of {"hook": ..., "onHookSuccess": ...}


class SessionStore:
    def __init__(self) -> None:
        self.hooks: Dict[HookEvent, List[SessionHookMatcher]] = {}


# Global session hooks state: session_id -> SessionStore
_session_hooks: Dict[str, SessionStore] = {}


def _get_or_create_store(session_id: str) -> SessionStore:
    if session_id not in _session_hooks:
        _session_hooks[session_id] = SessionStore()
    return _session_hooks[session_id]


def add_session_hook(
    set_app_state: Any,
    session_id: str,
    event: HookEvent,
    matcher: str,
    hook: Union[HookCommand, FunctionHook],
    on_hook_success: Optional[OnHookSuccess] = None,
    skill_root: Optional[str] = None,
) -> None:
    """Add a command or prompt hook to the session."""
    _add_hook_to_session(
        set_app_state, session_id, event, matcher, hook, on_hook_success, skill_root
    )


def add_function_hook(
    set_app_state: Any,
    session_id: str,
    event: HookEvent,
    matcher: str,
    callback: FunctionHookCallback,
    error_message: str,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Add a function hook to the session. Returns the hook ID."""
    hook_id = (options or {}).get("id") or f"function-hook-{int(time.time()*1000)}-{id(callback)}"
    hook = FunctionHook(
        callback=callback,
        error_message=error_message,
        hook_id=hook_id,
        timeout=(options or {}).get("timeout", 5000),
    )
    _add_hook_to_session(set_app_state, session_id, event, matcher, hook)
    return hook_id


def remove_function_hook(
    set_app_state: Any,
    session_id: str,
    event: HookEvent,
    hook_id: str,
) -> None:
    """Remove a function hook by ID from the session."""
    store = _session_hooks.get(session_id)
    if not store:
        return
    event_matchers = store.hooks.get(event, [])
    updated = []
    for m in event_matchers:
        new_hooks = [
            h for h in m.hooks
            if not (
                isinstance(h.get("hook"), FunctionHook)
                and h["hook"].id == hook_id
            )
        ]
        if new_hooks:
            updated.append(SessionHookMatcher(
                matcher=m.matcher,
                hooks=new_hooks,
                skill_root=m.skill_root,
            ))
    if updated:
        store.hooks[event] = updated
    elif event in store.hooks:
        del store.hooks[event]

    from ..log import log_for_debugging
    log_for_debugging(f"Removed function hook {hook_id} for event {event} in session {session_id}")


def _add_hook_to_session(
    set_app_state: Any,
    session_id: str,
    event: HookEvent,
    matcher: str,
    hook: Union[HookCommand, FunctionHook],
    on_hook_success: Optional[OnHookSuccess] = None,
    skill_root: Optional[str] = None,
) -> None:
    """Internal helper to add a hook to session state."""
    store = _get_or_create_store(session_id)
    event_matchers = store.hooks.get(event, [])

    existing_index = next(
        (i for i, m in enumerate(event_matchers)
         if m.matcher == matcher and m.skill_root == skill_root),
        -1,
    )

    if existing_index >= 0:
        event_matchers[existing_index].hooks.append({"hook": hook, "onHookSuccess": on_hook_success})
    else:
        event_matchers.append(
            SessionHookMatcher(
                matcher=matcher,
                hooks=[{"hook": hook, "onHookSuccess": on_hook_success}],
                skill_root=skill_root,
            )
        )
    store.hooks[event] = event_matchers

    from ..log import log_for_debugging
    log_for_debugging(f"Added session hook for event {event} in session {session_id}")


def remove_session_hook(
    set_app_state: Any,
    session_id: str,
    event: HookEvent,
    hook: HookCommand,
) -> None:
    """Remove a specific hook from the session."""
    from .hook_helpers import is_hook_equal
    store = _session_hooks.get(session_id)
    if not store:
        return
    event_matchers = store.hooks.get(event, [])
    updated = []
    for m in event_matchers:
        new_hooks = [h for h in m.hooks if not is_hook_equal(h["hook"], hook)]
        if new_hooks:
            updated.append(SessionHookMatcher(
                matcher=m.matcher, hooks=new_hooks, skill_root=m.skill_root
            ))
    if updated:
        store.hooks[event] = updated
    elif event in store.hooks:
        del store.hooks[event]

    from ..log import log_for_debugging
    log_for_debugging(f"Removed session hook for event {event} in session {session_id}")


def get_session_hooks(
    app_state: Any,
    session_id: str,
    event: Optional[HookEvent] = None,
) -> Dict[HookEvent, List[Dict[str, Any]]]:
    """Get all session hooks for a specific event (excluding function hooks)."""
    store = _session_hooks.get(session_id)
    if not store:
        return {}

    def convert(session_matchers: List[SessionHookMatcher]) -> List[Dict[str, Any]]:
        result = []
        for sm in session_matchers:
            hooks = [
                h["hook"] for h in sm.hooks
                if not isinstance(h["hook"], FunctionHook)
            ]
            result.append({
                "matcher": sm.matcher,
                "skillRoot": sm.skill_root,
                "hooks": hooks,
            })
        return result

    if event:
        matchers = store.hooks.get(event)
        if matchers:
            return {event: convert(matchers)}
        return {}

    return {
        evt: convert(matchers)
        for evt, matchers in store.hooks.items()
        if matchers
    }


def get_session_function_hooks(
    app_state: Any,
    session_id: str,
    event: Optional[HookEvent] = None,
) -> Dict[HookEvent, List[Dict[str, Any]]]:
    """Get all session function hooks for a specific event."""
    store = _session_hooks.get(session_id)
    if not store:
        return {}

    def extract(session_matchers: List[SessionHookMatcher]) -> List[Dict[str, Any]]:
        result = []
        for sm in session_matchers:
            fn_hooks = [
                h["hook"] for h in sm.hooks
                if isinstance(h["hook"], FunctionHook)
            ]
            if fn_hooks:
                result.append({"matcher": sm.matcher, "hooks": fn_hooks})
        return result

    if event:
        matchers = store.hooks.get(event)
        if matchers:
            fn = extract(matchers)
            return {event: fn} if fn else {}
        return {}

    return {
        evt: extract(matchers)
        for evt, matchers in store.hooks.items()
        if extract(matchers)
    }


def get_session_hook_callback(
    app_state: Any,
    session_id: str,
    event: HookEvent,
    matcher: str,
    hook: Union[HookCommand, FunctionHook],
) -> Optional[Dict[str, Any]]:
    """Get the full hook entry (including callbacks) for a specific session hook."""
    from .hook_helpers import is_hook_equal
    store = _session_hooks.get(session_id)
    if not store:
        return None
    event_matchers = store.hooks.get(event, [])
    for matcher_entry in event_matchers:
        if matcher_entry.matcher == matcher or matcher == "":
            for h in matcher_entry.hooks:
                if is_hook_equal(h["hook"], hook):
                    return h
    return None


def clear_session_hooks(set_app_state: Any, session_id: str) -> None:
    """Clear all session hooks for a specific session."""
    _session_hooks.pop(session_id, None)
    from ..log import log_for_debugging
    log_for_debugging(f"Cleared all session hooks for session {session_id}")
