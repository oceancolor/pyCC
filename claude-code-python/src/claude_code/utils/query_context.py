"""
Query context — metadata for a single LLM call.

Provides QueryContext dataclass, factory functions, and module-level
current-context state, mirroring queryContext.ts.
"""

from __future__ import annotations

import contextvars
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class QueryContext:
    """Metadata attached to one LLM query round-trip.

    Attributes:
        query_id:   Unique identifier for this query (UUID4 string).
        model:      Model name/ID used for the query (e.g. ``"claude-3-5-sonnet-..."``)
        cwd:        Working directory at the time the query was issued.
        session_id: Identifier for the containing session / conversation.
        start_time: Unix timestamp (float, seconds) when the query was created.
    """

    query_id: str
    model: str
    cwd: str
    session_id: str
    start_time: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since *start_time*."""
        return time.time() - self.start_time

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "model": self.model,
            "cwd": self.cwd,
            "session_id": self.session_id,
            "start_time": self.start_time,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"QueryContext(query_id={self.query_id!r}, model={self.model!r}, "
            f"session_id={self.session_id!r})"
        )


# ---------------------------------------------------------------------------
# Module-level state via contextvars (async-safe)
# ---------------------------------------------------------------------------

_current_query_context: contextvars.ContextVar[Optional[QueryContext]] = (
    contextvars.ContextVar("_current_query_context", default=None)
)

# Stable session ID shared across queries within the same process lifetime.
_session_id: str = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_query_context(
    model: str,
    cwd: str | None = None,
    session_id: str | None = None,
) -> QueryContext:
    """Create a new :class:`QueryContext` and set it as the current context.

    Args:
        model:      The model being called.
        cwd:        Working directory; defaults to ``os.getcwd()``.
        session_id: Session identifier; defaults to the module-level session ID.

    Returns:
        The newly created :class:`QueryContext`.  The context variable is also
        updated so :func:`get_current_query_context` returns it until replaced.
    """
    ctx = QueryContext(
        query_id=str(uuid.uuid4()),
        model=model,
        cwd=cwd if cwd is not None else os.getcwd(),
        session_id=session_id if session_id is not None else _session_id,
        start_time=time.time(),
    )
    _current_query_context.set(ctx)
    return ctx


def get_current_query_context() -> Optional[QueryContext]:
    """Return the :class:`QueryContext` set by the most recent
    :func:`create_query_context` call in the current async context,
    or ``None`` if no query has been started yet.
    """
    return _current_query_context.get()


def reset_session_id() -> str:
    """Generate and store a fresh session ID (useful for tests).

    Returns the new session ID string.
    """
    global _session_id
    _session_id = str(uuid.uuid4())
    return _session_id
