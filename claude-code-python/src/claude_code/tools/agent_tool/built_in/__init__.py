"""Built-in agent definitions for AgentTool.

Provides the pre-defined agent personas used by the AgentTool when spawning
sub-agents.  Each constant is a dict describing an agent type and its
system-prompt configuration.

Ported from: tools/AgentTool/built-in/ (TypeScript)

Exported constants
------------------
GENERAL_PURPOSE_AGENT
    The default open-ended sub-agent type.
EXPLORE_AGENT
    Read-only exploration agent used in plan mode.
PLAN_AGENT
    Planning agent that produces a structured action plan.
VERIFICATION_AGENT
    Verification agent that checks whether a task was completed correctly.
"""
from __future__ import annotations

from claude_code.tools.agent_tool.built_in.general_purpose_agent import GENERAL_PURPOSE_AGENT
from claude_code.tools.agent_tool.built_in.explore_agent import EXPLORE_AGENT
from claude_code.tools.agent_tool.built_in.plan_agent import PLAN_AGENT
from claude_code.tools.agent_tool.built_in.verification_agent import VERIFICATION_AGENT

__all__ = [
    "GENERAL_PURPOSE_AGENT",
    "EXPLORE_AGENT",
    "PLAN_AGENT",
    "VERIFICATION_AGENT",
]
