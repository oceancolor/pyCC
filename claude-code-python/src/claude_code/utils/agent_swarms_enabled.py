"""
Agent swarms (teammate) feature gate.
Ported from utils/agentSwarmsEnabled.ts
"""
from __future__ import annotations

import os
import sys


def _is_agent_teams_flag_set() -> bool:
    """Check if --agent-teams flag is in sys.argv."""
    return "--agent-teams" in sys.argv


def is_agent_swarms_enabled() -> bool:
    """Centralized runtime check for agent teams/teammate features.

    Ant builds: always enabled (USER_TYPE == 'ant').
    External builds require both:
      1. Opt-in via CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS env var OR --agent-teams flag
      2. GrowthBook gate 'tengu_amber_flint' enabled (killswitch)
    """
    if os.environ.get("USER_TYPE") == "ant":
        return True

    # External: require opt-in
    teams_env = os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "")
    if not (teams_env.lower() in ("1", "true", "yes") or _is_agent_teams_flag_set()):
        return False

    # Killswitch
    try:
        from claude_code.services.analytics.growthbook import (  # type: ignore
            get_feature_value_cached_may_be_stale,
        )
        if not get_feature_value_cached_may_be_stale("tengu_amber_flint", True):
            return False
    except ImportError:
        pass

    return True
