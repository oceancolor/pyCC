"""TeamDeleteTool. Ported from TeamDeleteTool/TeamDeleteTool.ts"""
from __future__ import annotations
import json
import os
import shutil
from typing import Any, Dict, Optional

TEAM_DELETE_TOOL_NAME = "TeamDelete"
TEAM_LEAD_NAME = "team-lead"


def _is_agent_swarms_enabled() -> bool:
    val = os.environ.get("CLAUDE_CODE_AGENT_SWARMS", "")
    return val.lower() in ("1", "true", "yes")


def _get_teams_base_dir() -> str:
    return os.environ.get("CLAUDE_CODE_TEAMS_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "teams"
    )


def _get_team_file_path(team_name: str) -> str:
    return os.path.join(_get_teams_base_dir(), f"{team_name}.json")


def _read_team_file(team_name: str) -> Optional[Dict[str, Any]]:
    path = _get_team_file_path(team_name)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.loads(fh.read())
    except Exception:
        return None


def _cleanup_team_directories(team_name: str) -> None:
    """Remove team metadata file and associated task directories."""
    # Remove team JSON
    team_path = _get_team_file_path(team_name)
    try:
        os.unlink(team_path)
    except OSError:
        pass

    # Remove team tasks directory
    tasks_base = os.environ.get("CLAUDE_CODE_TASKS_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "tasks"
    )
    import re
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", team_name)
    tasks_dir = os.path.join(tasks_base, sanitized)
    try:
        shutil.rmtree(tasks_dir, ignore_errors=True)
    except Exception:
        pass


class TeamDeleteTool:
    """Clean up team and task directories when the swarm is complete.

    Ported from TeamDeleteTool/TeamDeleteTool.ts.
    """

    name = TEAM_DELETE_TOOL_NAME
    search_hint = "disband a swarm team and clean up"
    max_result_size_chars = 100_000
    should_defer = True

    def is_enabled(self) -> bool:
        return _is_agent_swarms_enabled()

    async def description(self) -> str:
        return "Clean up team and task directories when the swarm is complete"

    async def call(self, context: Any = None, **_kwargs: Any) -> Dict[str, Any]:
        """Disband the current team and remove its files."""
        team_name: Optional[str] = None

        if context:
            app_state = getattr(context, "get_app_state", lambda: {})()
            team_name = (app_state or {}).get("teamContext", {}).get("teamName")

        if team_name:
            team_file = _read_team_file(team_name)
            if team_file:
                # Filter out the team lead; only count non-lead members
                members = team_file.get("members", [])
                non_lead = [m for m in members if m.get("name") != TEAM_LEAD_NAME]
                active = [m for m in non_lead if m.get("isActive") is not False]
                if active:
                    names = ", ".join(m.get("name", "?") for m in active)
                    return {
                        "data": {
                            "success": False,
                            "message": (
                                f"Cannot cleanup team with {len(active)} active member(s): "
                                f"{names}. Use requestShutdown to gracefully terminate "
                                "teammates first."
                            ),
                            "team_name": team_name,
                        }
                    }

            _cleanup_team_directories(team_name)

        # Clear team context from app state
        if context and callable(getattr(context, "set_app_state", None)):
            def _update(prev: Dict[str, Any]) -> Dict[str, Any]:
                updated = dict(prev)
                updated.pop("teamContext", None)
                updated["inbox"] = {"messages": []}
                return updated
            context.set_app_state(_update)

        return {
            "data": {
                "success": True,
                "message": (
                    f'Cleaned up directories and worktrees for team "{team_name}"'
                    if team_name
                    else "No team name found, nothing to clean up"
                ),
                "team_name": team_name,
            }
        }

    def map_tool_result(self, data: Dict[str, Any], tool_use_id: str) -> Dict[str, Any]:
        inner = data.get("data", data)
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": [{"type": "text", "text": json.dumps(inner)}],
        }
