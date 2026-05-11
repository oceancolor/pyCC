"""
Swarm Reconnection Module.

Handles initialization of swarm context for teammates.
- Fresh spawns: Initialize from CLI args (set via dynamicTeamContext)
- Resumed sessions: Initialize from teamName/agentName stored in the transcript

原始 TS: utils/swarm/reconnection.ts
"""

from typing import Any, Callable, Dict, Optional

from ..debug import log_for_debugging
from ..log import log_error
from ..teammate import get_dynamic_team_context
from .team_helpers import get_team_file_path, read_team_file


def compute_initial_team_context() -> Optional[Dict[str, Any]]:
    """Compute the initial teamContext for AppState.

    This is called synchronously during startup to compute the teamContext
    BEFORE the first render, eliminating the need for deferred workarounds.

    Returns:
        The teamContext dict to include in initialState, or None if not a teammate.
    """
    # dynamicTeamContext is set from CLI args
    context = get_dynamic_team_context()

    if not context:
        log_for_debugging(
            "[Reconnection] compute_initial_team_context: No teammate context set (not a teammate)"
        )
        return None

    team_name = getattr(context, "team_name", None) or getattr(context, "teamName", None)
    agent_name = getattr(context, "agent_name", None) or getattr(context, "agentName", None)

    if not team_name or not agent_name:
        log_for_debugging(
            "[Reconnection] compute_initial_team_context: No teammate context set (not a teammate)"
        )
        return None

    agent_id = getattr(context, "agent_id", None) or getattr(context, "agentId", None)

    # Read team file to get lead agent ID
    team_file = read_team_file(team_name)
    if not team_file:
        log_error(
            Exception(
                f"[compute_initial_team_context] Could not read team file for {team_name}"
            )
        )
        return None

    team_file_path = get_team_file_path(team_name)
    is_leader = not agent_id

    log_for_debugging(
        f"[Reconnection] Computed initial team context for "
        f"{'leader' if is_leader else f'teammate {agent_name}'} in team {team_name}"
    )

    return {
        "teamName": team_name,
        "teamFilePath": team_file_path,
        "leadAgentId": team_file.get("leadAgentId"),
        "selfAgentId": agent_id,
        "selfAgentName": agent_name,
        "isLeader": is_leader,
        "teammates": {},
    }


def initialize_teammate_context_from_session(
    set_app_state: Callable[[Callable[[Any], Any]], None],
    team_name: str,
    agent_name: str,
) -> None:
    """Initialize teammate context from a resumed session.

    This is called when resuming a session that has teamName/agentName stored
    in the transcript. It sets up teamContext in AppState so that heartbeat
    and other swarm features work correctly.

    Args:
        set_app_state: AppState setter function.
        team_name: Name of the team to resume.
        agent_name: Name of this agent within the team.
    """
    # Read team file to get lead agent ID
    team_file = read_team_file(team_name)
    if not team_file:
        log_error(
            Exception(
                f"[initialize_teammate_context_from_session] Could not read team file "
                f"for {team_name} (agent: {agent_name})"
            )
        )
        return

    # Find the member in the team file to get their agentId
    members = team_file.get("members", [])
    member = next((m for m in members if m.get("name") == agent_name), None)
    if not member:
        log_for_debugging(
            f"[Reconnection] Member {agent_name} not found in team {team_name} "
            f"- may have been removed"
        )

    agent_id = member.get("agentId") if member else None
    team_file_path = get_team_file_path(team_name)

    # Set teamContext in AppState
    def updater(prev: Any) -> Any:
        return {
            **prev,
            "teamContext": {
                "teamName": team_name,
                "teamFilePath": team_file_path,
                "leadAgentId": team_file.get("leadAgentId"),
                "selfAgentId": agent_id,
                "selfAgentName": agent_name,
                "isLeader": False,
                "teammates": {},
            },
        }

    set_app_state(updater)

    log_for_debugging(
        f"[Reconnection] Initialized agent context from session for "
        f"{agent_name} in team {team_name}"
    )
