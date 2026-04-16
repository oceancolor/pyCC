"""
load_agents_dir.py — Load agent definitions from filesystem.
Ported from AgentTool/loadAgentsDir.ts (755 lines).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

AgentMemoryScope = str  # 'user' | 'project' | 'local'
AgentMcpServerSpec = Union[str, Dict[str, Any]]

PERMISSION_MODES = ("default", "acceptEdits", "bypassPermissions", "plan")
EFFORT_LEVELS = ("low", "medium", "high")


@dataclass
class BaseAgentDefinition:
    agent_type: str
    when_to_use: str
    source: str = "custom"
    tools: Optional[List[str]] = None
    disallowed_tools: Optional[List[str]] = None
    skills: Optional[List[str]] = None
    mcp_servers: Optional[List[AgentMcpServerSpec]] = None
    hooks: Optional[Dict[str, Any]] = None
    color: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    permission_mode: Optional[str] = None
    max_turns: Optional[int] = None
    filename: Optional[str] = None
    base_dir: Optional[str] = None
    critical_system_reminder: Optional[str] = None
    required_mcp_servers: Optional[List[str]] = None
    background: bool = False
    initial_prompt: Optional[str] = None
    memory: Optional[AgentMemoryScope] = None
    isolation: Optional[str] = None
    pending_snapshot_update: Optional[Dict[str, str]] = None
    omit_claude_md: bool = False


@dataclass
class BuiltInAgentDefinition(BaseAgentDefinition):
    source: str = "built-in"
    base_dir: str = "built-in"
    get_system_prompt: Optional[Callable] = None
    callback: Optional[Callable] = None


@dataclass
class CustomAgentDefinition(BaseAgentDefinition):
    get_system_prompt: Optional[Callable] = None


@dataclass
class PluginAgentDefinition(BaseAgentDefinition):
    source: str = "plugin"
    get_system_prompt: Optional[Callable] = None
    plugin: str = ""


AgentDefinition = Union[BuiltInAgentDefinition, CustomAgentDefinition, PluginAgentDefinition]


@dataclass
class AgentDefinitionsResult:
    active_agents: List[AgentDefinition] = field(default_factory=list)
    all_agents: List[AgentDefinition] = field(default_factory=list)
    failed_files: Optional[List[Dict[str, str]]] = None
    allowed_agent_types: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Type guards
# ---------------------------------------------------------------------------

def is_built_in_agent(agent: AgentDefinition) -> bool:
    return getattr(agent, "source", None) == "built-in"


def is_custom_agent(agent: AgentDefinition) -> bool:
    source = getattr(agent, "source", "")
    return source not in ("built-in", "plugin")


def is_plugin_agent(agent: AgentDefinition) -> bool:
    return getattr(agent, "source", None) == "plugin"


# ---------------------------------------------------------------------------
# Active agent filtering
# ---------------------------------------------------------------------------

def get_active_agents_from_list(all_agents: List[AgentDefinition]) -> List[AgentDefinition]:
    """
    Deduplicate agents by agentType, with priority:
    built-in < plugin < user < project < flag < managed
    """
    groups = {
        "built-in": [],
        "plugin": [],
        "userSettings": [],
        "projectSettings": [],
        "flagSettings": [],
        "policySettings": [],
    }
    for agent in all_agents:
        src = getattr(agent, "source", "custom")
        groups.setdefault(src, []).append(agent)

    order = ["built-in", "plugin", "userSettings", "projectSettings",
             "flagSettings", "policySettings"]
    agent_map: Dict[str, AgentDefinition] = {}
    for key in order:
        for agent in groups.get(key, []):
            agent_type = getattr(agent, "agent_type", "")
            agent_map[agent_type] = agent

    return list(agent_map.values())


def has_required_mcp_servers(
    agent: AgentDefinition,
    available_servers: List[str],
) -> bool:
    """Check if all required MCP servers are available."""
    required = getattr(agent, "required_mcp_servers", None)
    if not required:
        return True
    available_lower = [s.lower() for s in available_servers]
    return all(
        any(pattern.lower() in srv for srv in available_lower)
        for pattern in required
    )


def filter_agents_by_mcp_requirements(
    agents: List[AgentDefinition],
    available_servers: List[str],
) -> List[AgentDefinition]:
    """Filter agents whose required MCP servers are available."""
    return [a for a in agents if has_required_mcp_servers(a, available_servers)]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _extract_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Extract YAML-style frontmatter from a markdown file."""
    if not content.startswith("---"):
        return {}, content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    frontmatter_text = content[3:end].strip()
    body = content[end + 4:].strip()

    frontmatter: Dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip()

    return frontmatter, body


def parse_agent_from_markdown(
    content: str,
    filename: str,
    source: str = "custom",
    base_dir: str = "",
) -> Optional[CustomAgentDefinition]:
    """
    Parse an agent definition from a markdown file.
    Mirrors parseAgentFromMarkdown() in loadAgentsDir.ts.
    """
    frontmatter, body = _extract_frontmatter(content)

    agent_type = frontmatter.get("name", "") or Path(filename).stem
    when_to_use = frontmatter.get("description", "") or frontmatter.get("whenToUse", "")

    if not when_to_use:
        # Try to extract from first non-empty paragraph
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                when_to_use = line[:200]
                break

    tools_raw = frontmatter.get("tools", "")
    tools: Optional[List[str]] = None
    if tools_raw:
        tools = [t.strip() for t in tools_raw.split(",") if t.strip()]

    model = frontmatter.get("model") or None
    permission_mode = frontmatter.get("permissionMode") or frontmatter.get("permission_mode") or None
    max_turns_raw = frontmatter.get("maxTurns") or frontmatter.get("max_turns")
    max_turns = int(max_turns_raw) if max_turns_raw else None

    skills_raw = frontmatter.get("skills", "")
    skills: Optional[List[str]] = None
    if skills_raw:
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()]

    system_prompt = body
    agent = CustomAgentDefinition(
        agent_type=agent_type,
        when_to_use=when_to_use,
        source=source,
        tools=tools,
        model=model,
        permission_mode=permission_mode,
        max_turns=max_turns,
        skills=skills,
        filename=filename,
        base_dir=base_dir,
        get_system_prompt=lambda: system_prompt,
    )
    return agent


def parse_agent_from_json(
    data: Dict[str, Any],
    agent_type: str,
    source: str = "custom",
    base_dir: str = "",
) -> Optional[CustomAgentDefinition]:
    """
    Parse an agent definition from a JSON object.
    Mirrors parseAgentFromJson() in loadAgentsDir.ts.
    """
    if not data.get("description") or not data.get("prompt"):
        return None

    system_prompt = data["prompt"]
    tools = data.get("tools")
    disallowed_tools = data.get("disallowedTools")
    model = data.get("model")
    permission_mode = data.get("permissionMode")
    max_turns = data.get("maxTurns")
    skills = data.get("skills")
    background = bool(data.get("background", False))
    initial_prompt = data.get("initialPrompt")
    memory = data.get("memory")
    hooks = data.get("hooks")

    return CustomAgentDefinition(
        agent_type=agent_type,
        when_to_use=data["description"],
        source=source,
        tools=tools,
        disallowed_tools=disallowed_tools,
        model=model,
        permission_mode=permission_mode,
        max_turns=max_turns,
        skills=skills,
        background=background,
        initial_prompt=initial_prompt,
        memory=memory,
        hooks=hooks,
        base_dir=base_dir,
        get_system_prompt=lambda: system_prompt,
    )


def parse_agents_from_json(
    data: Dict[str, Any],
    source: str = "custom",
    base_dir: str = "",
) -> List[CustomAgentDefinition]:
    """Parse multiple agents from a JSON record."""
    agents = []
    for agent_type, agent_data in data.items():
        if isinstance(agent_data, dict):
            agent = parse_agent_from_json(agent_data, agent_type, source, base_dir)
            if agent:
                agents.append(agent)
    return agents


# ---------------------------------------------------------------------------
# Directory loading
# ---------------------------------------------------------------------------

def _get_agent_dirs(cwd: str) -> List[Tuple[str, str]]:
    """
    Return (dir_path, source) pairs for agent definition directories.
    """
    dirs = []

    # Project-local: <cwd>/.claude/agents/
    project_dir = os.path.join(cwd, ".claude", "agents")
    if os.path.isdir(project_dir):
        dirs.append((project_dir, "projectSettings"))

    # User-level: ~/.claude/agents/
    user_dir = os.path.expanduser("~/.claude/agents")
    if os.path.isdir(user_dir):
        dirs.append((user_dir, "userSettings"))

    return dirs


def load_agents_from_dir(
    agents_dir: str,
    source: str = "custom",
) -> Tuple[List[CustomAgentDefinition], List[Dict[str, str]]]:
    """
    Load agent definitions from a directory.
    Supports .md (markdown) and .json files.
    Returns (agents, failed_files).
    """
    agents: List[CustomAgentDefinition] = []
    failed: List[Dict[str, str]] = []

    if not os.path.isdir(agents_dir):
        return agents, failed

    for filename in sorted(os.listdir(agents_dir)):
        filepath = os.path.join(agents_dir, filename)
        if not os.path.isfile(filepath):
            continue

        try:
            if filename.endswith(".md"):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                agent = parse_agent_from_markdown(
                    content, filename, source, agents_dir
                )
                if agent:
                    agents.append(agent)

            elif filename.endswith(".json") and filename != "agents.json":
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                agent_type = Path(filename).stem
                agent = parse_agent_from_json(data, agent_type, source, agents_dir)
                if agent:
                    agents.append(agent)

            elif filename == "agents.json":
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    batch = parse_agents_from_json(data, source, agents_dir)
                    agents.extend(batch)

        except Exception as e:
            failed.append({"path": filepath, "error": str(e)})

    return agents, failed


# ---------------------------------------------------------------------------
# Main entry point (with simple memoization)
# ---------------------------------------------------------------------------

_agents_cache: Dict[str, AgentDefinitionsResult] = {}


def clear_agent_definitions_cache() -> None:
    """Clear the memoized agent definitions cache."""
    _agents_cache.clear()


async def get_agent_definitions_with_overrides(cwd: str) -> AgentDefinitionsResult:
    """
    Load all agent definitions for the given working directory.
    Mirrors getAgentDefinitionsWithOverrides() in loadAgentsDir.ts.
    """
    if cwd in _agents_cache:
        return _agents_cache[cwd]

    all_agents: List[AgentDefinition] = []
    failed_files: List[Dict[str, str]] = []

    # Load built-in agents
    try:
        from claude_code.tools.agent_tool.built_in_agents import get_built_in_agents
        all_agents.extend(get_built_in_agents())
    except Exception:
        pass

    # Load from filesystem dirs
    for dir_path, source in _get_agent_dirs(cwd):
        agents, failed = load_agents_from_dir(dir_path, source)
        all_agents.extend(agents)
        failed_files.extend(failed)

    active_agents = get_active_agents_from_list(all_agents)

    result = AgentDefinitionsResult(
        active_agents=active_agents,
        all_agents=all_agents,
        failed_files=failed_files if failed_files else None,
    )
    _agents_cache[cwd] = result
    return result


def load_plugin_agents() -> List[PluginAgentDefinition]:
    """Load agents from plugin directories."""
    agents: List[PluginAgentDefinition] = []
    plugin_dirs = []

    # Check common plugin paths
    for base in [os.path.expanduser("~/.claude/plugins"), "/projects/.openclaw/plugins"]:
        if os.path.isdir(base):
            plugin_dirs.append(base)

    for plugin_dir in plugin_dirs:
        for plugin_name in os.listdir(plugin_dir):
            agents_dir = os.path.join(plugin_dir, plugin_name, "agents")
            if not os.path.isdir(agents_dir):
                continue
            loaded, _ = load_agents_from_dir(agents_dir, "plugin")
            for agent in loaded:
                plugin_agent = PluginAgentDefinition(
                    agent_type=agent.agent_type,
                    when_to_use=agent.when_to_use,
                    source="plugin",
                    plugin=plugin_name,
                    tools=agent.tools,
                    model=agent.model,
                    get_system_prompt=agent.get_system_prompt,
                    filename=agent.filename,
                    base_dir=agent.base_dir,
                )
                agents.append(plugin_agent)
    return agents
