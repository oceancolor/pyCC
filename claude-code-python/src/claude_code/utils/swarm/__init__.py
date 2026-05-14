"""Swarm (multi-agent) utilities sub-package. Ported from utils/swarm/.

Provides helpers for the Claude Code multi-agent swarm system including
team management, in-process runners, and permission synchronisation.
"""
from __future__ import annotations

from claude_code.utils.swarm.constants import get_swarm_socket_name
from claude_code.utils.swarm.team_helpers import (
    get_team_dir,
    sanitize_agent_name,
    sanitize_name,
)

__all__ = [
    "get_swarm_socket_name",
    "sanitize_name",
    "sanitize_agent_name",
    "get_team_dir",
]
