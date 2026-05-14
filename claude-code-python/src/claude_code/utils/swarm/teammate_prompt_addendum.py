"""Teammate system prompt addendum. Ported from utils/swarm/teammatePromptAddendum.ts"""

from __future__ import annotations

import os
from typing import Optional

TEAMMATE_SYSTEM_PROMPT_ADDENDUM = """
# Agent Teammate Communication

IMPORTANT: You are running as an agent in a team. To communicate with anyone on your team:
- Use the SendMessage tool with `to: "<name>"` to send messages to specific teammates
- Use the SendMessage tool with `to: "*"` sparingly for team-wide broadcasts

Just writing a response in text is not visible to others on your team - you MUST use the SendMessage tool.

The user interacts primarily with the team lead. Your work is coordinated through the task system and teammate messaging.
"""


def get_teammate_system_prompt_addendum(
    teammate_name: Optional[str] = None,
    leader_name: Optional[str] = None,
) -> str:
    """Return the teammate system prompt addendum, optionally customised with names.

    Args:
        teammate_name: The name of this teammate agent (used in personalised messages).
        leader_name: The name of the team leader agent.

    Returns:
        A multi-line system prompt section to append to the main system prompt.
    """
    addendum = TEAMMATE_SYSTEM_PROMPT_ADDENDUM.strip()

    lines = []
    if teammate_name:
        lines.append(f"\nYou are {teammate_name!r}, a member of the team.")
    if leader_name:
        lines.append(f"The team leader is {leader_name!r}. Coordinate with them for overall task direction.")

    if lines:
        addendum += "\n" + "\n".join(lines)

    return addendum


def should_include_teammate_addendum() -> bool:
    """Return True if the teammate system prompt addendum should be included.

    Based on whether swarm mode is enabled via environment variable.
    """
    return os.environ.get("CLAUDE_CODE_SWARM_MODE") == "1"
