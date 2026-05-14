"""Agent display utilities. Ported from AgentTool/agentDisplay.ts"""
from __future__ import annotations
from typing import Any

AGENT_SOURCE_GROUPS = [
    {"label": "User agents", "source": "userSettings"},
    {"label": "Project agents", "source": "projectSettings"},
    {"label": "Local agents", "source": "localSettings"},
    {"label": "Managed agents", "source": "policySettings"},
    {"label": "Plugin agents", "source": "plugin"},
    {"label": "CLI arg agents", "source": "flagSettings"},
    {"label": "Built-in agents", "source": "built-in"},
]


def resolve_agent_overrides(
    all_agents: list[dict[str, Any]],
    active_agents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Annotate agents with override info and deduplicate by (agentType, source)."""
    active_map: dict[str, dict[str, Any]] = {}
    for agent in active_agents:
        active_map[agent["agentType"]] = agent

    seen: set[str] = set()
    resolved: list[dict[str, Any]] = []

    for agent in all_agents:
        key = f"{agent['agentType']}::{agent.get('source', '')}"
        if key in seen:
            continue
        seen.add(key)

        result = dict(agent)
        active = active_map.get(agent["agentType"])
        if active is not None and active.get("source") != agent.get("source"):
            result["overriddenBy"] = active.get("source")
        resolved.append(result)

    return resolved


def format_agent_progress(agent_id: str, message: str) -> str:
    return f"[Agent:{agent_id}] {message}"


def format_agent_result(agent_id: str, result: str) -> str:
    return f"Agent {agent_id} completed:\n{result}"
