"""Agent memory persistence. Ported from AgentTool/agentMemory.ts"""
from __future__ import annotations
import os
from typing import Optional

AgentMemoryScope = str  # 'user' | 'project' | 'local'


def sanitize_agent_type_for_path(agent_type: str) -> str:
    return agent_type.replace(":", "-")


def get_local_agent_memory_dir(dir_name: str) -> str:
    remote = os.environ.get("CLAUDE_CODE_REMOTE_MEMORY_DIR")
    if remote:
        from claude_code.utils.path import sanitize_path
        cwd = os.getcwd()
        return os.path.join(remote, "projects", cwd, dir_name)
    cwd = os.getcwd()
    return os.path.join(cwd, ".claude", "agent-memory-local", dir_name)


def get_project_agent_memory_dir(dir_name: str) -> str:
    cwd = os.getcwd()
    return os.path.join(cwd, ".claude", "agent-memory", dir_name)


def get_user_agent_memory_dir(dir_name: str) -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude", "agent-memory", dir_name)


async def load_agent_memory_prompt(
    agent_type: str,
    scope: AgentMemoryScope = "project",
) -> Optional[str]:
    """Load persisted memory for an agent. Returns None if not found."""
    dir_name = sanitize_agent_type_for_path(agent_type)
    if scope == "local":
        mem_dir = get_local_agent_memory_dir(dir_name)
    elif scope == "user":
        mem_dir = get_user_agent_memory_dir(dir_name)
    else:
        mem_dir = get_project_agent_memory_dir(dir_name)
    index_file = os.path.join(mem_dir, "AGENT.md")
    if not os.path.exists(index_file):
        return None
    with open(index_file, "r", encoding="utf-8") as f:
        return f.read()
