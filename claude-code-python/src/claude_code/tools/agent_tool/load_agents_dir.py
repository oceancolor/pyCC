"""
Load agent definitions from filesystem.
Ported from AgentTool/loadAgentsDir.ts (755 lines → core).
"""
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional, TypedDict


class AgentDefinition(TypedDict, total=False):
    name: str
    description: str
    system_prompt: str
    tools: List[str]
    permission_mode: str
    effort: str
    memory_scope: str
    hooks: dict


class BuiltInAgentDefinition(AgentDefinition):
    pass


def load_plugin_agents() -> List[AgentDefinition]:
    """Load agents from plugin dirs. Stub."""
    return []


def load_agents_from_dir(agents_dir: str) -> List[AgentDefinition]:
    """Load .md agent definitions from a directory."""
    agents = []
    if not os.path.isdir(agents_dir):
        return agents
    for fname in os.listdir(agents_dir):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(agents_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            agent = _parse_agent_md(fname[:-3], content)
            agents.append(agent)
        except Exception:
            continue
    return agents


def _parse_agent_md(name: str, content: str) -> AgentDefinition:
    """Parse frontmatter + body from agent .md file."""
    import re
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    body = content
    frontmatter: dict = {}
    if fm_match:
        import yaml
        try:
            frontmatter = yaml.safe_load(fm_match.group(1)) or {}
        except Exception:
            pass
        body = content[fm_match.end():]
    return {
        "name": name,
        "description": frontmatter.get("description", ""),
        "system_prompt": body.strip(),
        "tools": frontmatter.get("tools", []),
        "permission_mode": frontmatter.get("permission_mode", "default"),
        "effort": frontmatter.get("effort", "normal"),
        "memory_scope": frontmatter.get("memory_scope", "project"),
    }


def is_built_in_agent(agent: AgentDefinition) -> bool:
    return agent.get("name", "").startswith("__")


_agents_cache: Optional[List[AgentDefinition]] = None


def get_all_agent_definitions() -> List[AgentDefinition]:
    global _agents_cache
    if _agents_cache is not None:
        return _agents_cache
    cwd = os.getcwd()
    agents = []
    # Try .claude/agents/
    agents += load_agents_from_dir(os.path.join(cwd, ".claude", "agents"))
    agents += load_agents_from_dir(os.path.join(os.path.expanduser("~"), ".claude", "agents"))
    agents += load_plugin_agents()
    _agents_cache = agents
    return agents


def find_agent_definition(name: str) -> Optional[AgentDefinition]:
    for agent in get_all_agent_definitions():
        if agent.get("name") == name:
            return agent
    return None
