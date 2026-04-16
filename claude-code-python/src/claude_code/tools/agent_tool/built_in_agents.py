"""Built-in agent registry. Ported from AgentTool/builtInAgents.ts"""
from __future__ import annotations
import os
from typing import List, Any

from claude_code.tools.agent_tool.built_in.general_purpose_agent import GENERAL_PURPOSE_AGENT
from claude_code.tools.agent_tool.built_in.explore_agent import EXPLORE_AGENT
from claude_code.tools.agent_tool.built_in.plan_agent import PLAN_AGENT


def are_explore_plan_agents_enabled() -> bool:
    return True  # Default enabled; GB flag stub


def get_built_in_agents() -> List[dict]:
    if os.environ.get("CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS", "").lower() in ("1", "true"):
        non_interactive = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "") in ("sdk-ts", "sdk-py", "sdk-cli")
        if non_interactive:
            return []

    agents: List[dict] = [dict(GENERAL_PURPOSE_AGENT)]

    if are_explore_plan_agents_enabled():
        agents.extend([dict(EXPLORE_AGENT), dict(PLAN_AGENT)])

    entrypoint = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")
    if entrypoint not in ("sdk-ts", "sdk-py", "sdk-cli"):
        pass  # could add CLAUDE_CODE_GUIDE_AGENT when available

    return agents
