"""
services/mcp/utils.py — MCP utility functions.
Ported from services/mcp/utils.ts (575 lines).

Filtering helpers, config hash, stale client removal, scope/transport utilities.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse


# ---------------------------------------------------------------------------
# Lazy imports to break circular dependencies
# ---------------------------------------------------------------------------

def _get_is_non_interactive_session() -> bool:
    try:
        from claude_code.bootstrap.state import get_is_non_interactive_session
        return get_is_non_interactive_session()
    except (ImportError, Exception):
        return False


def _get_global_claude_file() -> str:
    try:
        from claude_code.utils.env import get_global_claude_file
        return get_global_claude_file()
    except (ImportError, Exception):
        import os
        return os.path.expanduser("~/.claude/claude.json")


def _get_enterprise_mcp_file_path() -> str:
    try:
        from claude_code.services.mcp.config import get_enterprise_mcp_file_path
        return get_enterprise_mcp_file_path()
    except (ImportError, Exception):
        import os
        return os.path.expanduser("~/.claude/managed/managed-mcp.json")


def _get_mcp_config_by_name(name: str) -> Optional[dict]:
    try:
        from claude_code.services.mcp.config import get_mcp_config_by_name
        return get_mcp_config_by_name(name)
    except (ImportError, Exception):
        return None


def _normalize_name_for_mcp(name: str) -> str:
    try:
        from claude_code.services.mcp.normalization import normalize_mcp_server_name
        return normalize_mcp_server_name(name)
    except (ImportError, Exception):
        return name.strip().replace(" ", "_").lower()


def _mcp_info_from_string(tool_name: str) -> Optional[dict]:
    try:
        from claude_code.services.mcp.mcp_string_utils import from_mcp_tool_name
        server_name, tool = from_mcp_tool_name(tool_name)
        if server_name is None:
            return None
        return {"serverName": server_name, "toolName": tool}
    except (ImportError, Exception):
        if tool_name.startswith("mcp__"):
            rest = tool_name[5:]
            sep = rest.find("__")
            if sep >= 0:
                return {"serverName": rest[:sep], "toolName": rest[sep + 2:]}
        return None


def _get_settings_deprecated() -> dict:
    try:
        from claude_code.utils.settings.settings import get_settings_deprecated
        return get_settings_deprecated() or {}
    except (ImportError, Exception):
        return {}


def _has_skip_dangerous_mode_permission_prompt() -> bool:
    try:
        from claude_code.utils.settings.settings import has_skip_dangerous_mode_permission_prompt
        return has_skip_dangerous_mode_permission_prompt()
    except (ImportError, Exception):
        return False


def _is_setting_source_enabled(source: str) -> bool:
    try:
        from claude_code.utils.settings.constants import is_setting_source_enabled
        return is_setting_source_enabled(source)
    except (ImportError, Exception):
        return True


def _get_cwd() -> str:
    try:
        from claude_code.utils.cwd import get_cwd
        return get_cwd()
    except (ImportError, Exception):
        import os
        return os.getcwd()


def _json_stringify_stable(obj: Any) -> str:
    """JSON serialization with sorted keys (mirrors jsonStringify stable sort)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Tool / Command / Resource filtering helpers
# ---------------------------------------------------------------------------

def filter_tools_by_server(tools: list, server_name: str) -> list:
    """
    Filters tools by MCP server name.
    """
    prefix = f"mcp__{_normalize_name_for_mcp(server_name)}__"
    return [t for t in tools if (getattr(t, "name", None) or "").startswith(prefix)]


def command_belongs_to_server(command: Any, server_name: str) -> bool:
    """
    True when a command belongs to the given MCP server.
    MCP prompts: `mcp__<server>__<prompt>`.
    MCP skills: `<server>:<skill>`.
    """
    normalized = _normalize_name_for_mcp(server_name)
    name = getattr(command, "name", None) or (
        command.get("name") if isinstance(command, dict) else None
    )
    if not name:
        return False
    return (
        name.startswith(f"mcp__{normalized}__")
        or name.startswith(f"{normalized}:")
    )


def filter_commands_by_server(commands: list, server_name: str) -> list:
    """Filters commands by MCP server name."""
    return [c for c in commands if command_belongs_to_server(c, server_name)]


def filter_mcp_prompts_by_server(commands: list, server_name: str) -> list:
    """
    Filters MCP prompts (not skills) by server. Used by the /mcp menu.
    Skills set loadedFrom='mcp'; prompts don't (they use isMcp=True).
    """
    def is_prompt(c):
        tp = getattr(c, "type", None) or (c.get("type") if isinstance(c, dict) else None)
        loaded_from = getattr(c, "loadedFrom", None) or (
            c.get("loadedFrom") if isinstance(c, dict) else None
        )
        return not (tp == "prompt" and loaded_from == "mcp")

    return [
        c for c in commands
        if command_belongs_to_server(c, server_name) and is_prompt(c)
    ]


def filter_resources_by_server(resources: list, server_name: str) -> list:
    """Filters resources by MCP server name."""
    return [r for r in resources if (
        getattr(r, "server", None) or
        (r.get("server") if isinstance(r, dict) else None)
    ) == server_name]


def exclude_tools_by_server(tools: list, server_name: str) -> list:
    """Removes tools belonging to a specific MCP server."""
    prefix = f"mcp__{_normalize_name_for_mcp(server_name)}__"
    return [t for t in tools if not (getattr(t, "name", None) or "").startswith(prefix)]


def exclude_commands_by_server(commands: list, server_name: str) -> list:
    """Removes commands belonging to a specific MCP server."""
    return [c for c in commands if not command_belongs_to_server(c, server_name)]


def exclude_resources_by_server(
    resources: Dict[str, list],
    server_name: str,
) -> Dict[str, list]:
    """Removes resources belonging to a specific MCP server."""
    result = dict(resources)
    result.pop(server_name, None)
    return result


# ---------------------------------------------------------------------------
# Config hash
# ---------------------------------------------------------------------------

def hash_mcp_config(config: dict) -> str:
    """
    Stable hash of an MCP server config for change detection on /reload-plugins.
    Excludes `scope` (provenance, not content).
    Keys sorted so {a:1,b:2} and {b:2,a:1} hash the same.
    """
    rest = {k: v for k, v in config.items() if k != "scope"}
    stable = _json_stringify_stable(rest)
    return hashlib.sha256(stable.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# excludeStalePluginClients
# ---------------------------------------------------------------------------

def exclude_stale_plugin_clients(
    mcp: dict,
    configs: Dict[str, dict],
) -> dict:
    """
    Remove stale MCP clients and their tools/commands/resources.
    A client is stale if:
    - scope 'dynamic' and name no longer in configs (plugin disabled), or
    - config hash changed (args/url/env edited in .mcp.json) — any scope.

    Returns {clients, tools, commands, resources, stale}.
    """
    clients: list = mcp.get("clients", [])
    tools: list = list(mcp.get("tools", []))
    commands: list = list(mcp.get("commands", []))
    resources: dict = dict(mcp.get("resources", {}))

    stale = []
    for c in clients:
        c_name = getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None)
        c_config = getattr(c, "config", None) or (c.get("config") if isinstance(c, dict) else {})
        c_scope = c_config.get("scope") if isinstance(c_config, dict) else None

        fresh = configs.get(c_name) if c_name else None
        if not fresh:
            if c_scope == "dynamic":
                stale.append(c)
        elif hash_mcp_config(c_config) != hash_mcp_config(fresh):
            stale.append(c)

    if not stale:
        return {**mcp, "stale": []}

    for s in stale:
        s_name = getattr(s, "name", None) or (s.get("name") if isinstance(s, dict) else None)
        if s_name:
            tools = exclude_tools_by_server(tools, s_name)
            commands = exclude_commands_by_server(commands, s_name)
            resources = exclude_resources_by_server(resources, s_name)

    stale_names = {
        getattr(s, "name", None) or (s.get("name") if isinstance(s, dict) else None)
        for s in stale
    }
    remaining_clients = [
        c for c in clients
        if (getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None))
           not in stale_names
    ]

    return {
        "clients": remaining_clients,
        "tools": tools,
        "commands": commands,
        "resources": resources,
        "stale": stale,
    }


# ---------------------------------------------------------------------------
# isMcpTool / isMcpCommand
# ---------------------------------------------------------------------------

def is_tool_from_mcp_server(tool_name: str, server_name: str) -> bool:
    """Checks if a tool name belongs to a specific MCP server."""
    info = _mcp_info_from_string(tool_name)
    return info is not None and info.get("serverName") == server_name


def is_mcp_tool(tool: Any) -> bool:
    """Checks if a tool belongs to any MCP server."""
    name = getattr(tool, "name", None) or (tool.get("name") if isinstance(tool, dict) else None)
    is_mcp = getattr(tool, "isMcp", False) or (tool.get("isMcp") if isinstance(tool, dict) else False)
    return bool((name and name.startswith("mcp__")) or is_mcp)


def is_mcp_command(command: Any) -> bool:
    """Checks if a command belongs to any MCP server."""
    name = getattr(command, "name", None) or (command.get("name") if isinstance(command, dict) else None)
    is_mcp = getattr(command, "isMcp", False) or (command.get("isMcp") if isinstance(command, dict) else False)
    return bool((name and name.startswith("mcp__")) or is_mcp)


# ---------------------------------------------------------------------------
# Scope / config description
# ---------------------------------------------------------------------------

def describe_mcp_config_file_path(scope: str) -> str:
    """Describe the file path for a given MCP config scope."""
    import os
    if scope == "user":
        return _get_global_claude_file()
    elif scope == "project":
        return os.path.join(_get_cwd(), ".mcp.json")
    elif scope == "local":
        return f"{_get_global_claude_file()} [project: {_get_cwd()}]"
    elif scope == "dynamic":
        return "Dynamically configured"
    elif scope == "enterprise":
        return _get_enterprise_mcp_file_path()
    elif scope == "claudeai":
        return "claude.ai"
    else:
        return scope


def get_scope_label(scope: str) -> str:
    """Human-readable label for a config scope."""
    labels = {
        "local": "Local config (private to you in this project)",
        "project": "Project config (shared via .mcp.json)",
        "user": "User config (available in all your projects)",
        "dynamic": "Dynamic config (from command line)",
        "enterprise": "Enterprise config (managed by your organization)",
        "claudeai": "claude.ai config",
    }
    return labels.get(scope, scope)


def ensure_config_scope(scope: Optional[str] = None) -> str:
    """Validate and return a ConfigScope. Defaults to 'local'."""
    valid = ["local", "user", "project", "dynamic", "enterprise", "claudeai", "managed"]
    if not scope:
        return "local"
    if scope not in valid:
        raise ValueError(
            f"Invalid scope: {scope}. Must be one of: {', '.join(valid)}"
        )
    return scope


def ensure_transport(transport_type: Optional[str] = None) -> str:
    """Validate and return a transport type. Defaults to 'stdio'."""
    if not transport_type:
        return "stdio"
    if transport_type not in ("stdio", "sse", "http"):
        raise ValueError(
            f"Invalid transport type: {transport_type}. Must be one of: stdio, sse, http"
        )
    return transport_type


def parse_headers(header_array: List[str]) -> Dict[str, str]:
    """
    Parse a list of 'Header-Name: value' strings into a dict.
    Raises ValueError on invalid format.
    """
    headers: Dict[str, str] = {}
    for header in header_array:
        idx = header.find(":")
        if idx == -1:
            raise ValueError(
                f'Invalid header format: "{header}". Expected format: "Header-Name: value"'
            )
        key = header[:idx].strip()
        value = header[idx + 1:].strip()
        if not key:
            raise ValueError(
                f'Invalid header: "{header}". Header name cannot be empty.'
            )
        headers[key] = value
    return headers


# ---------------------------------------------------------------------------
# Project MCP server status
# ---------------------------------------------------------------------------

def get_project_mcp_server_status(server_name: str) -> str:
    """
    Returns 'approved' | 'rejected' | 'pending' for a project MCP server.
    """
    settings = _get_settings_deprecated()
    normalized_name = _normalize_name_for_mcp(server_name)

    disabled = settings.get("disabledMcpjsonServers") or []
    if any(_normalize_name_for_mcp(n) == normalized_name for n in disabled):
        return "rejected"

    enabled = settings.get("enabledMcpjsonServers") or []
    if (
        any(_normalize_name_for_mcp(n) == normalized_name for n in enabled)
        or settings.get("enableAllProjectMcpServers")
    ):
        return "approved"

    # In bypass permissions mode, auto-approve if projectSettings enabled.
    # SECURITY: only check hasSkipDangerousModePermissionPrompt, not sessionBypass.
    if (
        _has_skip_dangerous_mode_permission_prompt()
        and _is_setting_source_enabled("projectSettings")
    ):
        return "approved"

    # In non-interactive mode, auto-approve if projectSettings enabled.
    if _get_is_non_interactive_session() and _is_setting_source_enabled("projectSettings"):
        return "approved"

    return "pending"


def get_mcp_server_scope_from_tool_name(tool_name: str) -> Optional[str]:
    """
    Get the scope/settings source for an MCP server from a tool name.
    Returns ConfigScope or None if not an MCP tool or server not found.
    """
    # Quick check: is this an MCP tool?
    if not tool_name.startswith("mcp__"):
        try:
            # Check isMcp via tool dict
            tool_obj = {"name": tool_name}
            if not is_mcp_tool(tool_obj):
                return None
        except Exception:
            return None

    info = _mcp_info_from_string(tool_name)
    if not info:
        return None

    server_config = _get_mcp_config_by_name(info["serverName"])

    # Fallback: claude.ai servers have normalized names starting with "claude_ai_"
    if not server_config and info["serverName"].startswith("claude_ai_"):
        return "claudeai"

    return server_config.get("scope") if server_config else None


# ---------------------------------------------------------------------------
# Agent MCP server extraction
# ---------------------------------------------------------------------------

def extract_agent_mcp_servers(agents: list) -> list:
    """
    Extracts MCP server definitions from agent frontmatter and groups them by server name.
    Used to show agent-specific MCP servers in the /mcp command.
    Returns list of AgentMcpServerInfo dicts, sorted by name.
    """
    # Map: server name -> { config, sourceAgents }
    server_map: Dict[str, dict] = {}

    for agent in agents:
        mcp_servers = getattr(agent, "mcpServers", None) or (
            agent.get("mcpServers") if isinstance(agent, dict) else None
        )
        if not mcp_servers:
            continue

        agent_type = getattr(agent, "agentType", None) or (
            agent.get("agentType") if isinstance(agent, dict) else None
        )

        for spec in mcp_servers:
            # Skip string references — they refer to globally-configured servers
            if isinstance(spec, str):
                continue

            if not isinstance(spec, dict) or len(spec) != 1:
                continue

            server_name, server_config = next(iter(spec.items()))
            existing = server_map.get(server_name)

            if existing:
                if agent_type and agent_type not in existing["sourceAgents"]:
                    existing["sourceAgents"].append(agent_type)
            else:
                server_map[server_name] = {
                    "config": {**server_config, "name": server_name},
                    "sourceAgents": [agent_type] if agent_type else [],
                }

    result = []
    for name, entry in server_map.items():
        cfg = entry["config"]
        source_agents = entry["sourceAgents"]
        transport_type = cfg.get("type")

        if transport_type is None or transport_type == "stdio":
            result.append({
                "name": name,
                "sourceAgents": source_agents,
                "transport": "stdio",
                "command": cfg.get("command"),
                "needsAuth": False,
            })
        elif transport_type == "sse":
            result.append({
                "name": name,
                "sourceAgents": source_agents,
                "transport": "sse",
                "url": cfg.get("url"),
                "needsAuth": True,
            })
        elif transport_type == "http":
            result.append({
                "name": name,
                "sourceAgents": source_agents,
                "transport": "http",
                "url": cfg.get("url"),
                "needsAuth": True,
            })
        elif transport_type == "ws":
            result.append({
                "name": name,
                "sourceAgents": source_agents,
                "transport": "ws",
                "url": cfg.get("url"),
                "needsAuth": False,
            })
        # Skip internal types: sdk, claudeai-proxy, sse-ide, ws-ide

    return sorted(result, key=lambda x: x.get("name", ""))


# ---------------------------------------------------------------------------
# Logging-safe MCP base URL
# ---------------------------------------------------------------------------

def get_logging_safe_mcp_base_url(config: dict) -> Optional[str]:
    """
    Extracts the MCP server base URL (without query string) for analytics logging.
    Query strings are stripped because they can contain access tokens.
    Returns None for stdio/sdk servers or if URL parsing fails.
    """
    url = config.get("url")
    if not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url)
        cleaned = urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, "", ""
        ))
        return cleaned.rstrip("/")
    except Exception:
        return None
