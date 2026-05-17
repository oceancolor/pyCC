"""Speculative prompt execution service.

Ported from services/PromptSuggestion/speculation.ts

Speculation pre-runs the model against a guessed next user message so that, if
the user's actual message matches the guess, the response can be served
immediately without a round-trip.

In this Python port most of the React / file-overlay machinery is omitted;
the module exposes the key public surface (enable check, start, abort, accept)
with lightweight implementations that can be wired into a full agent later.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

SpeculationStatus = Literal["idle", "running", "completed", "aborted"]


@dataclass
class SpeculationState:
    """Holds the current speculation execution state."""

    status: SpeculationStatus = "idle"
    speculated_prompt: Optional[str] = None
    result_messages: List[Any] = field(default_factory=list)
    abort_controller: Optional[Any] = None


# Module-level singleton
_state = SpeculationState()

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

_SPECULATION_ENV = "CLAUDE_CODE_ENABLE_SPECULATION"


def is_speculation_enabled() -> bool:
    """Return True if speculative execution is enabled.

    Reads ``CLAUDE_CODE_ENABLE_SPECULATION`` env var; defaults to False so
    that speculation is opt-in during the Python port.
    """
    val = os.environ.get(_SPECULATION_ENV, "").strip().lower()
    return val in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------

def prepare_messages_for_injection(messages: List[Any]) -> List[Any]:
    """Return *messages* prepared for injection into a speculated conversation.

    In the TypeScript version this strips certain system markers; here we
    return a shallow copy to avoid mutation of the caller's list.
    """
    return list(messages)


async def start_speculation(
    prompt: str,
    messages: Optional[List[Any]] = None,
    model: Optional[str] = None,
    app_state: Optional[Dict[str, Any]] = None,
) -> Optional[SpeculationState]:
    """Begin speculative execution for *prompt*.

    Returns the updated :class:`SpeculationState` or ``None`` if speculation
    is disabled or a run is already in progress.
    """
    if not is_speculation_enabled():
        return None
    if _state.status == "running":
        return None  # Already speculating

    _state.status = "running"
    _state.speculated_prompt = prompt
    _state.result_messages = []

    # Actual model call would happen here in a full implementation.
    # For now we resolve immediately with no result so downstream code
    # can wire in real logic without breaking.
    _state.status = "completed"
    return _state


async def accept_speculation(
    actual_prompt: str,
    state: Optional[SpeculationState] = None,
) -> bool:
    """Accept a completed speculation if *actual_prompt* matches the guess.

    Returns True if the speculated result was accepted and can be used.
    """
    target = state or _state
    if target.status != "completed":
        return False
    if target.speculated_prompt != actual_prompt:
        # Prompt diverged – discard speculation
        abort_speculation()
        return False
    return True


def abort_speculation(set_app_state: Any = None) -> None:
    """Abort any in-flight speculation run."""
    if _state.abort_controller is not None:
        try:
            _state.abort_controller.abort()
        except Exception:
            pass
    _state.status = "aborted"
    _state.speculated_prompt = None
    _state.result_messages = []
    _state.abort_controller = None


async def handle_speculation_accept(
    actual_prompt: str,
    app_state: Optional[Dict[str, Any]] = None,
    set_app_state: Any = None,
) -> bool:
    """High-level handler: check & accept or abort speculation."""
    return await accept_speculation(actual_prompt)


# ---------------------------------------------------------------------------
# Backward-compat alias
# ---------------------------------------------------------------------------

async def speculate(
    prompt: str,
    model: Optional[str] = None,
) -> Optional[str]:
    """Simple async entry point kept for backward compatibility.

    Returns the speculated response text, or ``None`` if unavailable.
    """
    state = await start_speculation(prompt, model=model)
    if state is None or not state.result_messages:
        return None
    # Extract text from the first result message if possible
    msg = state.result_messages[0] if state.result_messages else None
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        return msg.get("text") or msg.get("content")
    return None
