"""Agent color management. Ported from tools/AgentTool/agentColorManager.ts"""
from __future__ import annotations
from typing import Dict, List, Optional

AgentColorName = str

AGENT_COLORS: List[AgentColorName] = [
    "blue", "green", "yellow", "magenta", "cyan",
    "red", "white", "brightBlue", "brightGreen", "brightYellow",
]

AGENT_COLOR_TO_THEME_COLOR: Dict[str, str] = {
    "blue": "blue",
    "green": "green",
    "yellow": "yellow",
    "magenta": "magenta",
    "cyan": "cyan",
    "red": "red",
    "white": "white",
    "brightBlue": "blueBright",
    "brightGreen": "greenBright",
    "brightYellow": "yellowBright",
}

_assigned: Dict[str, AgentColorName] = {}
_next_index = 0


def assign_agent_color(agent_id: str) -> AgentColorName:
    global _next_index
    if agent_id not in _assigned:
        _assigned[agent_id] = AGENT_COLORS[_next_index % len(AGENT_COLORS)]
        _next_index += 1
    return _assigned[agent_id]


def get_agent_color(agent_id: str) -> Optional[AgentColorName]:
    return _assigned.get(agent_id)


def reset_agent_colors() -> None:
    global _next_index
    _assigned.clear()
    _next_index = 0
