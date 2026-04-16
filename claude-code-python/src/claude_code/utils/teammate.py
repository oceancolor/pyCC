# Source: utils/teammate.ts + teammateContext.ts
"""
Teammate utilities for agent swarm coordination.

Identifies whether this Claude Code instance is running as a spawned teammate
in a swarm. Context can come from environment variables or runtime configuration.

Priority order for identity resolution:
1. Runtime context (set via set_dynamic_team_context)
2. Environment variables (CLAUDE_CODE_AGENT_ID, CLAUDE_CODE_TEAM_NAME, etc.)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Teammate:
    """
    Identity and configuration for a single agent in a swarm.
    Mirrors TeammateContext from teammateContext.ts.
    """

    agent_id: str
    name: str
    role: str = ""
    color: Optional[str] = None
    team_name: str = ""
    plan_mode_required: bool = False
    parent_session_id: Optional[str] = None

    def is_valid(self) -> bool:
        """A teammate is valid if it has both agent_id and team_name."""
        return bool(self.agent_id and self.team_name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "color": self.color,
            "team_name": self.team_name,
            "plan_mode_required": self.plan_mode_required,
            "parent_session_id": self.parent_session_id,
        }


# ---------------------------------------------------------------------------
# Dynamic runtime context (mirrors dynamicTeamContext in TS)
# ---------------------------------------------------------------------------

_dynamic_team_context: Optional[Teammate] = None


def set_dynamic_team_context(context: Optional[Teammate]) -> None:
    """Set the dynamic team context (called when joining a team at runtime)."""
    global _dynamic_team_context
    _dynamic_team_context = context


def clear_dynamic_team_context() -> None:
    """Clear the dynamic team context (called when leaving a team)."""
    global _dynamic_team_context
    _dynamic_team_context = None


def get_dynamic_team_context() -> Optional[Teammate]:
    """Get the current dynamic team context (for inspection/debugging)."""
    return _dynamic_team_context


# ---------------------------------------------------------------------------
# Environment variable helpers
# ---------------------------------------------------------------------------


def _is_env_truthy(value: Optional[str]) -> bool:
    """Mirror isEnvTruthy from envUtils.ts."""
    if not value:
        return False
    return value.strip().lower() not in ("0", "false", "no", "")


def _teammate_from_env() -> Optional[Teammate]:
    """
    Build a Teammate from environment variables.
    Mirrors CLI args --agent-id / --team-name / etc. stored as env vars.
    """
    agent_id = os.environ.get("CLAUDE_CODE_AGENT_ID", "")
    team_name = os.environ.get("CLAUDE_CODE_TEAM_NAME", "")
    agent_name = os.environ.get("CLAUDE_CODE_AGENT_NAME", agent_id)
    color = os.environ.get("CLAUDE_CODE_AGENT_COLOR") or None
    plan_mode = _is_env_truthy(os.environ.get("CLAUDE_CODE_PLAN_MODE_REQUIRED"))
    parent_session = os.environ.get("CLAUDE_CODE_PARENT_SESSION_ID") or None

    if not (agent_id and team_name):
        return None

    return Teammate(
        agent_id=agent_id,
        name=agent_name,
        team_name=team_name,
        color=color,
        plan_mode_required=plan_mode,
        parent_session_id=parent_session,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_current_teammate() -> Optional[Teammate]:
    """
    Return the current agent's Teammate info, or None if not in a swarm.

    Priority:
    1. _dynamic_team_context (set via set_dynamic_team_context)
    2. Environment variables
    """
    if _dynamic_team_context is not None:
        return _dynamic_team_context
    return _teammate_from_env()


def is_teammate() -> bool:
    """Returns True if this session is running as a teammate in a swarm."""
    t = get_current_teammate()
    return t is not None and t.is_valid()


def get_agent_id() -> Optional[str]:
    """Returns the agent ID, or None if not in a swarm."""
    if _dynamic_team_context:
        return _dynamic_team_context.agent_id
    return os.environ.get("CLAUDE_CODE_AGENT_ID") or None


def get_agent_name() -> Optional[str]:
    """Returns the agent name, or None if not in a swarm."""
    if _dynamic_team_context:
        return _dynamic_team_context.name
    name = os.environ.get("CLAUDE_CODE_AGENT_NAME")
    if name:
        return name
    return os.environ.get("CLAUDE_CODE_AGENT_ID") or None


def get_team_name(team_context: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Returns the team name, or None.
    Pass team_context={"teamName": "..."} from AppState for leader support.
    """
    if _dynamic_team_context:
        return _dynamic_team_context.team_name or None
    env_team = os.environ.get("CLAUDE_CODE_TEAM_NAME")
    if env_team:
        return env_team
    if team_context:
        return team_context.get("teamName") or None
    return None


def get_teammate_color() -> Optional[str]:
    """Returns the teammate's assigned color, or None."""
    if _dynamic_team_context:
        return _dynamic_team_context.color
    return os.environ.get("CLAUDE_CODE_AGENT_COLOR") or None


def get_parent_session_id() -> Optional[str]:
    """Returns the parent session ID for this teammate, or None."""
    if _dynamic_team_context:
        return _dynamic_team_context.parent_session_id
    return os.environ.get("CLAUDE_CODE_PARENT_SESSION_ID") or None


def is_plan_mode_required() -> bool:
    """Returns True if this teammate must enter plan mode before implementing."""
    if _dynamic_team_context is not None:
        return _dynamic_team_context.plan_mode_required
    return _is_env_truthy(os.environ.get("CLAUDE_CODE_PLAN_MODE_REQUIRED"))


def is_team_lead(team_context: Optional[Dict[str, str]] = None) -> bool:
    """
    Returns True if this session is the team lead.
    A session is the lead if its agent_id matches team_context["leadAgentId"],
    or if no agent_id is set (backwards compat).
    """
    if not team_context:
        return False
    lead_agent_id = team_context.get("leadAgentId")
    if not lead_agent_id:
        return False
    my_agent_id = get_agent_id()
    if my_agent_id == lead_agent_id:
        return True
    # Backwards compat: no agent ID → original session that created the team
    if not my_agent_id:
        return True
    return False


def parse_teammate_config(config: Dict[str, Any]) -> Optional[Teammate]:
    """
    Parse a teammate configuration dict into a Teammate dataclass.

    Expected keys (all optional except agent_id + team_name):
        agent_id / agentId
        name / agentName
        role
        color
        team_name / teamName
        plan_mode_required / planModeRequired
        parent_session_id / parentSessionId
    """
    if not config:
        return None

    def _get(*keys: str) -> Any:
        for k in keys:
            if k in config:
                return config[k]
        return None

    agent_id = str(_get("agent_id", "agentId") or "").strip()
    team_name = str(_get("team_name", "teamName") or "").strip()

    if not (agent_id and team_name):
        return None

    name = str(_get("name", "agentName") or agent_id).strip()
    role = str(_get("role") or "").strip()
    color_raw = _get("color")
    color = str(color_raw).strip() if color_raw else None

    plan_raw = _get("plan_mode_required", "planModeRequired")
    plan_mode_required: bool
    if isinstance(plan_raw, bool):
        plan_mode_required = plan_raw
    elif isinstance(plan_raw, str):
        plan_mode_required = _is_env_truthy(plan_raw)
    else:
        plan_mode_required = bool(plan_raw)

    parent_raw = _get("parent_session_id", "parentSessionId")
    parent_session_id = str(parent_raw).strip() if parent_raw else None

    return Teammate(
        agent_id=agent_id,
        name=name,
        role=role,
        color=color,
        team_name=team_name,
        plan_mode_required=plan_mode_required,
        parent_session_id=parent_session_id,
    )
