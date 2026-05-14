"""Turn-scoped workload tag via contextvars. Ported from workloadContext.ts.

WHY a separate module from bootstrap/state.py:
bootstrap is transitively imported by browser-sdk entry-points, and the
browser bundle cannot import asyncio hooks.  This module is only imported
from CLI/SDK code paths that never end up in a restricted runtime.

WHY contextvars (not a global mutable slot):
void-detached background agents (forked slash commands, AgentTool) yield at
their first await.  The parent turn's synchronous continuation runs to
completion BEFORE the detached closure resumes.  A global set_workload('cron')
at the top of the closure is deterministically clobbered.  ContextVar captures
context at invocation time and survives every await in that chain, isolated
from the parent — the same pattern as agentContext.py.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Callable, Literal, Optional, TypeVar

__all__ = [
    "Workload",
    "WORKLOAD_CRON",
    "get_workload",
    "run_with_workload",
    "set_workload",
    "reset_workload",
]

#: Server-side sanitizer accepts only lowercase [a-z0-9_-]{0,32}.
Workload = Literal["cron"]
WORKLOAD_CRON: Workload = "cron"

T = TypeVar("T")

_workload_var: ContextVar[Optional[str]] = ContextVar("workload", default=None)


def get_workload() -> Optional[str]:
    """Return the workload tag for the current async context, or None."""
    return _workload_var.get()


def run_with_workload(workload: Optional[str], fn: Callable[[], T]) -> T:
    """Wrap *fn* in a workload context.

    ALWAYS establishes a new context boundary, even when *workload* is None.
    This prevents leaked cron tags from propagating into the next turn's
    scheduling chain (see TypeScript source for the full analysis).
    """
    token: Token[Optional[str]] = _workload_var.set(workload)
    try:
        return fn()
    finally:
        _workload_var.reset(token)


def set_workload(workload: Optional[str]) -> Token:
    """Directly set the workload for the current context.

    Returns a Token that can be passed to reset_workload() to restore the
    previous value.  Prefer run_with_workload() for scoped usage.
    """
    return _workload_var.set(workload)


def reset_workload(token: Token) -> None:
    """Restore the workload to the value captured in *token*."""
    _workload_var.reset(token)


def is_cron_workload() -> bool:
    """Return True if the current context is tagged as a cron workload."""
    return get_workload() == WORKLOAD_CRON
