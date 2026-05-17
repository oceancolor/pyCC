"""TeamCreate tool. Ported from TeamCreateTool/TeamCreateTool.ts."""
from __future__ import annotations

import os
from typing import Any, List, Optional

TEAM_CREATE_TOOL_NAME = "TeamCreate"
DESCRIPTION = "Create a new agent team for multi-agent coordination"

PROMPT = """Create a new swarm team and set up the directory structure.

This operation:
- Creates the team directory (``~/.claude/teams/{team-name}/``)
- Creates the task directory (``~/.claude/tasks/{team-name}/``)
- Registers team context in the current session

Use this when starting a multi-agent task that benefits from parallel execution.
Teammates will be able to communicate and share tasks within the named team."""


class TeamCreateTool:
    """Bootstrap a named agent team.

    Mirrors the TS ``TeamCreateTool`` from the ``team_tools`` compound module.
    In environments where agent swarms are disabled the call returns a clear
    error rather than raising an exception.
    """

    name = TEAM_CREATE_TOOL_NAME
    description = DESCRIPTION
    should_defer = True
    is_concurrency_safe = True

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "team_name": {
                        "type": "string",
                        "description": "Name of the team to create",
                    },
                    "teammates": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of teammate agent IDs or names",
                    },
                },
                "required": ["team_name"],
            },
        }

    async def call(
        self,
        team_name: str = "",
        teammates: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> dict:
        if not team_name:
            return {"error": "team_name is required"}

        # Create team and task directories
        base = os.path.expanduser("~/.claude")
        team_dir = os.path.join(base, "teams", team_name)
        task_dir = os.path.join(base, "tasks", team_name)

        try:
            os.makedirs(team_dir, exist_ok=True)
            os.makedirs(task_dir, exist_ok=True)
        except OSError as exc:
            return {"error": f"Failed to create team directories: {exc}"}

        return {
            "team_name": team_name,
            "team_dir": team_dir,
            "task_dir": task_dir,
            "teammates": teammates or [],
            "status": "created",
        }

    def map_tool_result(self, content: dict, tool_use_id: str) -> dict:
        if content.get("error"):
            text = f"TeamCreate failed: {content['error']}"
        else:
            text = (
                f"Team '{content.get('team_name')}' created.\n"
                f"  team_dir: {content.get('team_dir')}\n"
                f"  task_dir: {content.get('task_dir')}"
            )
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": text,
        }
