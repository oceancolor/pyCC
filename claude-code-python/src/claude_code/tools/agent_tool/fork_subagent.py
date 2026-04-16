"""Fork subagent feature. Ported from AgentTool/forkSubagent.ts"""
from __future__ import annotations
import os

FORK_SUBAGENT_TYPE = "fork"


def is_fork_subagent_enabled() -> bool:
    """Check if fork subagent experiment is enabled."""
    return os.environ.get("CLAUDE_CODE_FORK_SUBAGENT", "").lower() in ("1", "true")


FORK_AGENT = {
    "name": FORK_SUBAGENT_TYPE,
    "description": "Implicit fork agent that inherits parent context",
    "tools": ["*"],
    "permission_mode": "bubble",
    "use_exact_tools": True,
}
