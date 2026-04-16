"""
Agent swarms / teammate feature flag. Ported from agentSwarmsEnabled.ts
"""
from __future__ import annotations
import os
import sys


def _is_agent_teams_flag_set() -> bool:
    return "--agent-teams" in sys.argv


def is_agent_swarms_enabled() -> bool:
    """Check if agent teams/teammate features are enabled."""
    if os.environ.get("USER_TYPE") == "ant":
        return True
    if not (os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "").lower() in ("1", "true", "yes")
            or _is_agent_teams_flag_set()):
        return False
    # Killswitch: always allowed when running internally
    return True


def is_unary_logging_enabled() -> bool:
    """Stub for unary event logging feature flag."""
    return False
