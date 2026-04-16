"""AgentTool prompt. Ported from AgentTool/prompt.ts"""
from __future__ import annotations

AGENT_TOOL_NAME = "Agent"

DESCRIPTION = (
    "Launches a new agent to carry out a sub-task in parallel.\n\n"
    "Usage:\n"
    "- Use for tasks that need multiple steps and can run independently\n"
    "- Each agent has its own context, tools, and working directory\n"
    "- Agents can read/write files and run commands\n"
    "- The parent agent continues while sub-agents run in the background"
)

DEFAULT_AGENT_PROMPT = (
    "You are an AI assistant helping with a sub-task delegated from a parent agent. "
    "Complete the task described and report back."
)
