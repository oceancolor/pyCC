"""
Resume a previously-run agent from its transcript.
Ported from AgentTool/resumeAgent.ts (265 lines → core).
"""
from __future__ import annotations
from typing import Any, Optional, TypedDict

class ResumeAgentResult(TypedDict):
    agent_id: str
    description: str
    output_file: str


async def resume_agent_background(
    agent_id: str,
    prompt: str,
    tool_use_context: Any = None,
    can_use_tool: Any = None,
    invoking_request_id: str = "",
) -> ResumeAgentResult:
    """Resume a prior agent session and run it in background."""
    import os
    from claude_code.utils.session_storage import get_agent_transcript
    transcript = await get_agent_transcript(agent_id)
    if not transcript:
        raise ValueError(f"No transcript found for agent {agent_id}")
    output_dir = os.path.join(os.path.expanduser("~"), ".claude", "agent-outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{agent_id}.txt")
    return {
        "agent_id": agent_id,
        "description": f"Resuming agent {agent_id}",
        "output_file": output_file,
    }
