"""AgentTool constants.

Ported from: tools/AgentTool/constants.ts

Defines the canonical tool name, backward-compatible legacy name, and
the set of one-shot built-in agent types whose parent agent omits the
agentId/SendMessage/usage trailer to save tokens.
"""
from __future__ import annotations

#: The current wire name for the agent tool.
AGENT_TOOL_NAME: str = "Agent"

#: Legacy wire name kept for backward compatibility with permission rules,
#: hooks, and resumed sessions that still reference the old "Task" name.
LEGACY_AGENT_TOOL_NAME: str = "Task"

#: Agent type identifier used for the verification sub-agent.
VERIFICATION_AGENT_TYPE: str = "verification"

#: Built-in agent types that run once and return a report.
#: The parent never sends follow-up messages, so the agentId/SendMessage/usage
#: trailer is skipped to save tokens (~135 chars × 34 M Explore runs/week).
ONE_SHOT_BUILTIN_AGENT_TYPES: frozenset[str] = frozenset(["Explore", "Plan"])

__all__ = [
    "AGENT_TOOL_NAME",
    "LEGACY_AGENT_TOOL_NAME",
    "VERIFICATION_AGENT_TYPE",
    "ONE_SHOT_BUILTIN_AGENT_TYPES",
]
