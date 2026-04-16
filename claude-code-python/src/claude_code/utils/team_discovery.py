"""
team_discovery.py - Team discovery utilities.

Ported from teamDiscovery.ts.

Scans ~/.claude/teams/ to find teams and teammate statuses.
Used by the Teams UI to show team status (swarm / multi-agent view).

In this Python port the swarm/tmux-specific fields are preserved as data
classes for type safety.  The actual team file reading is stubbed out via
`read_team_file` — replace with a real implementation when the full swarm
module is ported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data types (mirrors TS type aliases)
# ---------------------------------------------------------------------------

PaneBackendType = str  # e.g. 'tmux', 'docker', etc.


@dataclass
class TeamSummary:
    name: str
    member_count: int
    running_count: int
    idle_count: int


@dataclass
class TeammateStatus:
    name: str
    agent_id: str
    tmux_pane_id: str
    cwd: str
    status: str  # 'running' | 'idle' | 'unknown'
    agent_type: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    color: Optional[str] = None
    idle_since: Optional[str] = None  # ISO timestamp
    worktree_path: Optional[str] = None
    is_hidden: bool = False
    backend_type: Optional[PaneBackendType] = None
    mode: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TEAMS_DIR = Path.home() / ".claude" / "teams"
_VALID_BACKEND_TYPES = {"tmux", "docker", "ssh", "local"}


def _is_pane_backend(value: str) -> bool:
    return value in _VALID_BACKEND_TYPES


def _read_team_file(team_name: str) -> Optional[dict]:
    """
    Read the team JSON file from ~/.claude/teams/<team_name>.json.
    Returns None if the file doesn't exist or can't be parsed.
    """
    team_path = _TEAMS_DIR / f"{team_name}.json"
    try:
        return json.loads(team_path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_teammate_statuses(team_name: str) -> List[TeammateStatus]:
    """
    Return detailed teammate statuses for *team_name*.

    Reads ``isActive`` from the team config to determine running/idle status.
    The team-lead member is excluded from the results.
    """
    team_file = _read_team_file(team_name)
    if not team_file:
        return []

    hidden_pane_ids: set = set(team_file.get("hiddenPaneIds") or [])
    statuses: List[TeammateStatus] = []

    for member in team_file.get("members", []):
        if member.get("name") == "team-lead":
            continue

        is_active: bool = member.get("isActive", True) is not False
        status = "running" if is_active else "idle"

        backend_raw = member.get("backendType", "")
        backend: Optional[PaneBackendType] = (
            backend_raw if backend_raw and _is_pane_backend(backend_raw) else None
        )

        tmux_pane_id: str = member.get("tmuxPaneId", "")
        statuses.append(
            TeammateStatus(
                name=member.get("name", ""),
                agent_id=member.get("agentId", ""),
                agent_type=member.get("agentType"),
                model=member.get("model"),
                prompt=member.get("prompt"),
                status=status,
                color=member.get("color"),
                tmux_pane_id=tmux_pane_id,
                cwd=member.get("cwd", ""),
                worktree_path=member.get("worktreePath"),
                is_hidden=tmux_pane_id in hidden_pane_ids,
                backend_type=backend,
                mode=member.get("mode"),
            )
        )

    return statuses
