"""Agent display formatting. Ported from AgentTool/agentDisplay.ts"""
from __future__ import annotations
from typing import Any

def format_agent_progress(agent_id: str, message: str) -> str:
    return f"[Agent:{agent_id}] {message}"

def format_agent_result(agent_id: str, result: str) -> str:
    return f"Agent {agent_id} completed:\n{result}"
