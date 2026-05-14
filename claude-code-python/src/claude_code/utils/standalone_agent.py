"""Standalone agent utilities. Ported from utils/standaloneAgent.ts

These helpers provide access to standalone agent context (name and color)
for sessions that are NOT part of a swarm team. When a session is part
of a swarm, these functions return None to let swarm context take precedence.
"""

from __future__ import annotations

from typing import Any, Optional


def _get_team_name() -> Optional[str]:
    """Return the swarm team name if this session is part of a team."""
    try:
        from claude_code.utils.teammate import get_team_name
        return get_team_name()
    except ImportError:
        pass
    try:
        import os
        return os.environ.get("CLAUDE_CODE_TEAM_NAME") or None
    except Exception:
        return None


def get_standalone_agent_name(app_state: Any) -> Optional[str]:
    """Return the standalone agent name if set and not in a swarm.

    Uses get_team_name() for consistency with is_teammate() swarm detection.

    Args:
        app_state: Application state object with a ``standalone_agent_context``
                   attribute (dict or object with a ``name`` field).

    Returns:
        The agent name string, or None if in a team or no name is set.
    """
    if _get_team_name():
        return None
    ctx: Any
    if isinstance(app_state, dict):
        ctx = app_state.get("standaloneAgentContext") or app_state.get("standalone_agent_context")
    else:
        ctx = getattr(app_state, "standalone_agent_context", None) or getattr(
            app_state, "standaloneAgentContext", None
        )
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        return ctx.get("name") or None
    return getattr(ctx, "name", None) or None


def get_standalone_agent_color(app_state: Any) -> Optional[str]:
    """Return the standalone agent color if set and not in a swarm.

    Returns None when part of a swarm team.
    """
    if _get_team_name():
        return None
    if isinstance(app_state, dict):
        ctx = app_state.get("standaloneAgentContext") or app_state.get("standalone_agent_context")
    else:
        ctx = getattr(app_state, "standalone_agent_context", None) or getattr(
            app_state, "standaloneAgentContext", None
        )
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        return ctx.get("color") or None
    return getattr(ctx, "color", None) or None


def is_standalone_agent(app_state: Any) -> bool:
    """Return True if this session has standalone agent context set."""
    return get_standalone_agent_name(app_state) is not None
