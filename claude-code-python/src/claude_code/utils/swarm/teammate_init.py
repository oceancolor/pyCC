"""
Teammate Initialization Module.

Handles initialization for Claude Code instances running as teammates in a swarm.
Registers a Stop hook to notify the team leader when the teammate becomes idle.

原始 TS: utils/swarm/teammateInit.ts
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional

from ..debug import log_for_debugging
from .team_helpers import read_team_file, set_member_active


def initialize_teammate_hooks(
    set_app_state: Callable[[Callable[[Any], Any]], None],
    session_id: str,
    team_info: Dict[str, str],
) -> None:
    """Initialize hooks for a teammate running in a swarm.

    Should be called early in session startup after AppState is available.

    Registers a Stop hook that sends an idle notification to the team leader
    when this teammate's session stops.

    Args:
        set_app_state: AppState setter function.
        session_id: Current session ID.
        team_info: Dict with teamName, agentId, agentName keys.
    """
    team_name = team_info.get("teamName", "")
    agent_id = team_info.get("agentId", "")
    agent_name = team_info.get("agentName", "")

    # Read team file to get leader ID
    team_file = read_team_file(team_name)
    if not team_file:
        log_for_debugging(
            f"[TeammateInit] Team file not found for team: {team_name}"
        )
        return

    lead_agent_id = team_file.get("leadAgentId")

    # Apply team-wide allowed paths if any exist
    team_allowed_paths: List[Dict[str, Any]] = team_file.get("teamAllowedPaths") or []
    if team_allowed_paths:
        log_for_debugging(
            f"[TeammateInit] Found {len(team_allowed_paths)} team-wide allowed path(s)"
        )
        for allowed_path in team_allowed_paths:
            path_value = allowed_path.get("path", "")
            tool_name = allowed_path.get("toolName", "")
            # For absolute paths, prepend one / to create //path/** pattern
            if path_value.startswith("/"):
                rule_content = f"/{path_value}/**"
            else:
                rule_content = f"{path_value}/**"

            log_for_debugging(
                f"[TeammateInit] Applying team permission: {tool_name} allowed in "
                f"{path_value} (rule: {rule_content})"
            )

            def _make_updater(tn: str, rc: str) -> Callable[[Any], Any]:
                def updater(prev: Any) -> Any:
                    try:
                        from ..permissions.permission_update import apply_permission_update  # type: ignore
                        if isinstance(prev, dict):
                            ctx = prev.get("toolPermissionContext", {})
                            new_ctx = apply_permission_update(
                                ctx,
                                {
                                    "type": "addRules",
                                    "rules": [{"toolName": tn, "ruleContent": rc}],
                                    "behavior": "allow",
                                    "destination": "session",
                                },
                            )
                            return {**prev, "toolPermissionContext": new_ctx}
                    except (ImportError, Exception):
                        pass
                    return prev
                return updater

            set_app_state(_make_updater(tool_name, rule_content))

    # Find the leader's name from the members array
    members = team_file.get("members", [])
    lead_member = next(
        (m for m in members if m.get("agentId") == lead_agent_id), None
    )
    lead_agent_name = lead_member.get("name", "team-lead") if lead_member else "team-lead"

    # Don't register hook if this agent is the leader
    if agent_id == lead_agent_id:
        log_for_debugging(
            "[TeammateInit] This agent is the team leader - skipping idle notification hook"
        )
        return

    log_for_debugging(
        f"[TeammateInit] Registering Stop hook for teammate {agent_name} "
        f"to notify leader {lead_agent_name}"
    )

    # Register Stop hook to notify leader when this teammate stops
    _register_stop_hook(
        set_app_state,
        session_id,
        team_name,
        agent_name,
        lead_agent_name,
    )


def _register_stop_hook(
    set_app_state: Callable[[Callable[[Any], Any]], None],
    session_id: str,
    team_name: str,
    agent_name: str,
    lead_agent_name: str,
) -> None:
    """Register a Stop hook that sends an idle notification to the team leader."""

    async def _stop_hook(messages: Any, _signal: Any) -> bool:
        # Mark this teammate as idle in the team config (fire and forget)
        asyncio.ensure_future(set_member_active(team_name, agent_name, False))

        # Send idle notification to the team leader
        try:
            from ..teammate_mailbox import (
                create_idle_notification,
                write_to_mailbox,
            )
            from ..teammate import get_teammate_color
            from ..slow_operations import json_stringify

            def _get_last_peer_dm_summary(msgs: Any) -> Optional[str]:
                try:
                    from ..teammate_mailbox import get_last_peer_dm_summary  # type: ignore
                    return get_last_peer_dm_summary(msgs)
                except (ImportError, Exception):
                    return None

            notification = create_idle_notification(
                agent_name,
                idle_reason="available",
                summary=_get_last_peer_dm_summary(messages),
            )
            import time
            await write_to_mailbox(
                lead_agent_name,
                {
                    "from": agent_name,
                    "text": json_stringify(notification),
                    "timestamp": _iso_now(),
                    "color": get_teammate_color(),
                },
            )
            log_for_debugging(
                f"[TeammateInit] Sent idle notification to leader {lead_agent_name}"
            )
        except (ImportError, Exception) as e:
            log_for_debugging(
                f"[TeammateInit] Failed to send idle notification: {e}"
            )

        return True  # Don't block the Stop

    # Register the hook
    try:
        from ..hooks.session_hooks import add_function_hook  # type: ignore
        add_function_hook(
            set_app_state,
            session_id,
            "Stop",
            "",  # No matcher - applies to all Stop events
            _stop_hook,
            "Failed to send idle notification to team leader",
            timeout=10000,
        )
    except (ImportError, Exception) as e:
        log_for_debugging(
            f"[TeammateInit] Could not register Stop hook: {e}"
        )


def _iso_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    import datetime
    return datetime.datetime.utcnow().isoformat() + "Z"
