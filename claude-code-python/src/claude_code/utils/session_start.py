"""
session_start.py - Session start hook processing.

Ported from sessionStart.ts. Manages session lifecycle hooks:
- processSessionStartHooks: execute hooks on session start/resume/clear/compact
- processSetupHooks: execute hooks on init/maintenance triggers
- takeInitialUserMessage: consume pending initial user message from hooks
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, AsyncIterator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class SessionStartSource(str, Enum):
    STARTUP = "startup"
    RESUME = "resume"
    CLEAR = "clear"
    COMPACT = "compact"


class SetupTrigger(str, Enum):
    INIT = "init"
    MAINTENANCE = "maintenance"


@dataclass
class HookResultMessage:
    """Represents a message returned by a hook execution."""
    content: str
    hook_name: str = ""
    hook_event: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """Raw result from executing a single hook."""
    message: Optional[HookResultMessage] = None
    additional_contexts: list[str] = field(default_factory=list)
    initial_user_message: Optional[str] = None
    watch_paths: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Global state (side-channel for initial user message)
# Mirrors TS: `let pendingInitialUserMessage: string | undefined`
# ---------------------------------------------------------------------------

_pending_initial_user_message: Optional[str] = None


def take_initial_user_message() -> Optional[str]:
    """
    Consume and return the pending initial user message set by hooks.
    Returns None if no message is pending. Clears the value on read.
    """
    global _pending_initial_user_message
    v = _pending_initial_user_message
    _pending_initial_user_message = None
    return v


def _set_initial_user_message(msg: str) -> None:
    global _pending_initial_user_message
    _pending_initial_user_message = msg


# ---------------------------------------------------------------------------
# Hook executor stubs
# These are dependency-injected in production; stubs used for standalone use.
# ---------------------------------------------------------------------------

async def _default_session_start_hook_executor(
    source: str,
    session_id: Optional[str],
    agent_type: Optional[str],
    model: Optional[str],
    force_sync: bool,
) -> AsyncIterator[HookResult]:
    """Default no-op hook executor. Override via set_hook_executors()."""
    return
    yield  # make it an async generator


async def _default_setup_hook_executor(
    trigger: str,
    force_sync: bool,
) -> AsyncIterator[HookResult]:
    """Default no-op setup hook executor."""
    return
    yield


# Mutable references so tests can inject custom executors
_session_start_executor: Callable[..., AsyncIterator[HookResult]] = (
    _default_session_start_hook_executor
)
_setup_executor: Callable[..., AsyncIterator[HookResult]] = (
    _default_setup_hook_executor
)


def set_hook_executors(
    session_start: Optional[Callable[..., AsyncIterator[HookResult]]] = None,
    setup: Optional[Callable[..., AsyncIterator[HookResult]]] = None,
) -> None:
    """Inject custom hook executors (used in tests and production wiring)."""
    global _session_start_executor, _setup_executor
    if session_start is not None:
        _session_start_executor = session_start
    if setup is not None:
        _setup_executor = setup


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

async def process_session_start_hooks(
    source: SessionStartSource | str,
    session_id: Optional[str] = None,
    agent_type: Optional[str] = None,
    model: Optional[str] = None,
    force_sync_execution: bool = False,
) -> list[HookResultMessage]:
    """
    Execute SessionStart hooks for the given source event.

    Collects hook messages, additional context strings, watch paths,
    and an optional initialUserMessage side-channel value.

    Returns list of HookResultMessage to be injected into the conversation.
    """
    hook_messages: list[HookResultMessage] = []
    additional_contexts: list[str] = []
    all_watch_paths: list[str] = []

    try:
        async for hook_result in _session_start_executor(
            str(source),
            session_id,
            agent_type,
            model,
            force_sync_execution,
        ):
            if hook_result.message:
                hook_messages.append(hook_result.message)
            if hook_result.additional_contexts:
                additional_contexts.extend(hook_result.additional_contexts)
            if hook_result.initial_user_message:
                _set_initial_user_message(hook_result.initial_user_message)
            if hook_result.watch_paths:
                all_watch_paths.extend(hook_result.watch_paths)
    except Exception as exc:
        logger.warning("Error executing session start hooks: %s", exc)

    if all_watch_paths:
        _update_watch_paths(all_watch_paths)

    if additional_contexts:
        ctx_msg = HookResultMessage(
            content="\n".join(additional_contexts),
            hook_name="SessionStart",
            hook_event="SessionStart",
            metadata={"type": "hook_additional_context"},
        )
        hook_messages.append(ctx_msg)

    return hook_messages


async def process_setup_hooks(
    trigger: SetupTrigger | str,
    force_sync_execution: bool = False,
) -> list[HookResultMessage]:
    """
    Execute Setup hooks for init or maintenance triggers.

    Returns list of HookResultMessage.
    """
    hook_messages: list[HookResultMessage] = []
    additional_contexts: list[str] = []

    try:
        async for hook_result in _setup_executor(
            str(trigger),
            force_sync_execution,
        ):
            if hook_result.message:
                hook_messages.append(hook_result.message)
            if hook_result.additional_contexts:
                additional_contexts.extend(hook_result.additional_contexts)
    except Exception as exc:
        logger.warning("Error executing setup hooks: %s", exc)

    if additional_contexts:
        ctx_msg = HookResultMessage(
            content="\n".join(additional_contexts),
            hook_name="Setup",
            hook_event="Setup",
            metadata={"type": "hook_additional_context"},
        )
        hook_messages.append(ctx_msg)

    return hook_messages


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _update_watch_paths(paths: list[str]) -> None:
    """Register file watch paths. Stub — wire to actual watcher in production."""
    logger.debug("Watch paths updated: %s", paths)
