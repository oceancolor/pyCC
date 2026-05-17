"""Built-in agent definitions for AgentTool."""
from claude_code.tools.agent_tool.built_in.general_purpose_agent import GENERAL_PURPOSE_AGENT
from claude_code.tools.agent_tool.built_in.explore_agent import EXPLORE_AGENT
from claude_code.tools.agent_tool.built_in.plan_agent import PLAN_AGENT
from claude_code.tools.agent_tool.built_in.verification_agent import VERIFICATION_AGENT

__all__ = ["GENERAL_PURPOSE_AGENT", "EXPLORE_AGENT", "PLAN_AGENT", "VERIFICATION_AGENT"]
