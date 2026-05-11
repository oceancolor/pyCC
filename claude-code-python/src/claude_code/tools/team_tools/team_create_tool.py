"""TeamCreateTool. Ported from TeamCreateTool/TeamCreateTool.ts"""
from __future__ import annotations
import json
import os
import time
from typing import Any, Dict, Optional

TEAM_CREATE_TOOL_NAME = "TeamCreate"
TEAM_LEAD_NAME = "team-lead"


def _is_agent_swarms_enabled() -> bool:
    """Check if agent swarms feature is enabled."""
    val = os.environ.get("CLAUDE_CODE_AGENT_SWARMS", "")
    return val.lower() in ("1", "true", "yes")


def _get_team_file_path(team_name: str) -> str:
    """Return the path for a team's JSON metadata file."""
    base = os.environ.get("CLAUDE_CODE_TEAMS_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "teams"
    )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{team_name}.json")


def _read_team_file(team_name: str) -> Optional[Dict[str, Any]]:
    path = _get_team_file_path(team_name)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.loads(fh.read())
    except Exception:
        return None


def _write_team_file(team_name: str, data: Dict[str, Any]) -> None:
    path = _get_team_file_path(team_name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=2))


def _sanitize_name(name: str) -> str:
    """Replace non-alphanumeric chars with underscores for safe use as IDs."""
    import re
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def _generate_word_slug() -> str:
    """Generate a short random slug."""
    import uuid
    return str(uuid.uuid4())[:8]


def _format_agent_id(role: str, team_name: str) -> str:
    return f"{role}@{team_name}"


def _generate_unique_team_name(provided_name: str) -> str:
    if not _read_team_file(provided_name):
        return provided_name
    return _generate_word_slug()


class TeamCreateTool:
    """Create a new team for coordinating multiple agents.

    Ported from TeamCreateTool/TeamCreateTool.ts.
    """

    name = TEAM_CREATE_TOOL_NAME
    search_hint = "create a multi-agent swarm team"
    max_result_size_chars = 100_000
    should_defer = True

    def is_enabled(self) -> bool:
        return _is_agent_swarms_enabled()

    async def description(self) -> str:
        return "Create a new team for coordinating multiple agents"

    async def validate_input(
        self,
        team_name: str,
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        if not team_name or not team_name.strip():
            return {
                "result": False,
                "message": "team_name is required for TeamCreate",
                "error_code": 9,
            }
        return {"result": True}

    async def call(
        self,
        team_name: str,
        description: Optional[str] = None,
        agent_type: Optional[str] = None,
        context: Any = None,
    ) -> Dict[str, Any]:
        """Create a new team and initialise its metadata file."""
        if not _is_agent_swarms_enabled():
            raise RuntimeError("Agent swarms are not enabled in this environment")

        # Check if already leading a team
        if context:
            app_state = getattr(context, "get_app_state", lambda: {})()
            existing_team = (app_state or {}).get("teamContext", {}).get("teamName")
            if existing_team:
                raise RuntimeError(
                    f'Already leading team "{existing_team}". '
                    "A leader can only manage one team at a time. "
                    "Use TeamDelete to end the current team before creating a new one."
                )

        final_name = _generate_unique_team_name(team_name)
        lead_agent_id = _format_agent_id(TEAM_LEAD_NAME, final_name)
        lead_agent_type = agent_type or TEAM_LEAD_NAME
        team_file_path = _get_team_file_path(final_name)

        team_file: Dict[str, Any] = {
            "name": final_name,
            "description": description,
            "createdAt": int(time.time() * 1000),
            "leadAgentId": lead_agent_id,
            "members": [
                {
                    "agentId": lead_agent_id,
                    "name": TEAM_LEAD_NAME,
                    "agentType": lead_agent_type,
                    "joinedAt": int(time.time() * 1000),
                    "cwd": os.getcwd(),
                }
            ],
        }

        _write_team_file(final_name, team_file)

        # Update app state if context supports it
        if context and callable(getattr(context, "set_app_state", None)):
            def _update(prev: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    **prev,
                    "teamContext": {
                        "teamName": final_name,
                        "teamFilePath": team_file_path,
                        "leadAgentId": lead_agent_id,
                        "teammates": {
                            lead_agent_id: {
                                "name": TEAM_LEAD_NAME,
                                "agentType": lead_agent_type,
                                "cwd": os.getcwd(),
                                "spawnedAt": int(time.time() * 1000),
                            }
                        },
                    },
                }
            context.set_app_state(_update)

        return {
            "data": {
                "team_name": final_name,
                "team_file_path": team_file_path,
                "lead_agent_id": lead_agent_id,
            }
        }

    def map_tool_result(self, data: Dict[str, Any], tool_use_id: str) -> Dict[str, Any]:
        inner = data.get("data", data)
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": [{"type": "text", "text": json.dumps(inner)}],
        }
