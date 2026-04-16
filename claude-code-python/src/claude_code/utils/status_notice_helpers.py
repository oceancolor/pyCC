"""Status notice helpers. Ported from statusNoticeHelpers.ts"""
from __future__ import annotations
from typing import Any, Optional

AGENT_DESCRIPTIONS_THRESHOLD = 15_000

def get_agent_descriptions_total_tokens(agent_definitions: Optional[Any] = None) -> int:
    if not agent_definitions:
        return 0
    agents = getattr(agent_definitions, 'active_agents', [])
    if not agents and isinstance(agent_definitions, dict):
        agents = agent_definitions.get('activeAgents', [])
    total = 0
    for agent in agents:
        src = getattr(agent, 'source', None) or (agent.get('source') if isinstance(agent, dict) else None)
        if src == 'built-in':
            continue
        agent_type = getattr(agent, 'agent_type', None) or (agent.get('agentType','') if isinstance(agent, dict) else '')
        when = getattr(agent, 'when_to_use', None) or (agent.get('whenToUse','') if isinstance(agent, dict) else '')
        desc = f"{agent_type}: {when}"
        total += len(desc) // 4  # rough token estimate
    return total
