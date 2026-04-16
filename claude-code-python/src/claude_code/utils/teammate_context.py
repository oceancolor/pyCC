"""
TeammateContext - Runtime context for in-process teammates.

Python equivalent uses contextvars.ContextVar (analogous to Node's
AsyncLocalStorage) to enable concurrent teammate execution without
global-state conflicts.

Relationship with other teammate identity mechanisms:
- Env vars (CLAUDE_CODE_AGENT_ID): Process-based teammates spawned via tmux
- dynamic_team_context (teammate.py): Process-based teammates joining at runtime
- TeammateContext (this module): In-process teammates via ContextVar
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Callable, Optional, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class TeammateContext:
    """Runtime context for in-process teammates."""

    # Full agent ID, e.g. "researcher@my-team"
    agent_id: str
    # Display name, e.g. "researcher"
    agent_name: str
    # Team name this teammate belongs to
    team_name: str
    # Whether teammate must enter plan mode before implementing
    plan_mode_required: bool
    # Leader's session ID (for transcript correlation)
    parent_session_id: str
    # Discriminator — always True for in-process teammates
    is_in_process: bool = field(default=True, init=False)
    # UI color assigned to this teammate (optional)
    color: Optional[str] = None

    # Note: AbortController → threading.Event or asyncio.Event in Python.
    # Stored as Any to avoid forcing a specific concurrency model on callers.
    abort_controller: Optional[object] = None


# ---------------------------------------------------------------------------
# ContextVar storage  (replaces AsyncLocalStorage)
# ---------------------------------------------------------------------------

_teammate_context_var: contextvars.ContextVar[Optional[TeammateContext]] = (
    contextvars.ContextVar("teammate_context", default=None)
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_teammate_context() -> Optional[TeammateContext]:
    """Return the current in-process teammate context, or None."""
    return _teammate_context_var.get()


def is_in_process_teammate() -> bool:
    """Return True if executing within an in-process teammate context."""
    return _teammate_context_var.get() is not None


def run_with_teammate_context(context: TeammateContext, fn: Callable[[], T]) -> T:
    """Run *fn* with *context* set as the active teammate context.

    Uses a ContextVar token so that nested/concurrent calls are isolated.

    Args:
        context: The teammate context to activate.
        fn: Zero-argument callable to invoke.

    Returns:
        The return value of *fn*.
    """
    token = _teammate_context_var.set(context)
    try:
        return fn()
    finally:
        _teammate_context_var.reset(token)


def create_teammate_context(
    *,
    agent_id: str,
    agent_name: str,
    team_name: str,
    plan_mode_required: bool,
    parent_session_id: str,
    color: Optional[str] = None,
    abort_controller: Optional[object] = None,
) -> TeammateContext:
    """Create a TeammateContext from keyword arguments.

    Args:
        agent_id: Full agent identifier (e.g. "researcher@my-team").
        agent_name: Short display name (e.g. "researcher").
        team_name: Name of the team this teammate belongs to.
        plan_mode_required: Whether the teammate must enter plan mode first.
        parent_session_id: Leader's session ID for transcript correlation.
        color: Optional UI color string.
        abort_controller: Optional abort/cancel controller object.

    Returns:
        A fully constructed TeammateContext.
    """
    return TeammateContext(
        agent_id=agent_id,
        agent_name=agent_name,
        team_name=team_name,
        plan_mode_required=plan_mode_required,
        parent_session_id=parent_session_id,
        color=color,
        abort_controller=abort_controller,
    )
