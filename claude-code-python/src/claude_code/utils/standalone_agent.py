"""Standalone agent utilities. Ported from standaloneAgent.ts.

These helpers provide access to standalone agent context (name and color)
for sessions that are NOT part of a swarm team.  When a session is part of
a swarm, these functions return None to let swarm context take precedence.
"""
from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "get_standalone_agent_name",
    "get_standalone_agent_color",
    "get_standalone_agent_context",
    "is_standalone_agent",
]


def _get_team_name() -> Optional[str]:
    """Lazy import to avoid circular dependencies."""
    try:
        from claude_code.utils.teammate import get_team_name  # type: ignore[import]

        return get_team_name()
    except Exception:
        return None


def get_standalone_agent_context(app_state: Any) -> Optional[dict]:
    """Return the standaloneAgentContext dict from *app_state*, or None."""
    ctx = getattr(app_state, "standalone_agent_context", None)
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        return ctx
    # Support dataclass/namedtuple-like objects
    return {
        "name": getattr(ctx, "name", None),
        "color": getattr(ctx, "color", None),
    }


def get_standalone_agent_name(app_state: Any) -> Optional[str]:
    """Return the standalone agent name if set and not a swarm teammate.

    Uses get_team_name() for consistency with is_teammate() swarm detection.
    Returns None if in a swarm or no standalone name is configured.
    """
    if _get_team_name():
        return None
    ctx = get_standalone_agent_context(app_state)
    if ctx is None:
        return None
    return ctx.get("name")


def get_standalone_agent_color(app_state: Any) -> Optional[str]:
    """Return the standalone agent theme color if set and not a swarm teammate.

    Returns None if in a swarm or no color is configured.
    """
    if _get_team_name():
        return None
    ctx = get_standalone_agent_context(app_state)
    if ctx is None:
        return None
    return ctx.get("color")


def is_standalone_agent(app_state: Any) -> bool:
    """Return True if this session is configured as a standalone (non-swarm) agent."""
    return get_standalone_agent_name(app_state) is not None
