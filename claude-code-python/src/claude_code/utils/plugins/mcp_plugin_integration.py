"""
MCP plugin integration - integrates MCP (Model Context Protocol) plugins.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_mcp_plugin_configs() -> List[Dict[str, Any]]:
    """Get MCP server configurations from installed plugins."""
    configs: List[Dict[str, Any]] = []
    try:
        from .plugin_directories import get_plugin_repos_dir
        import os, json
        base = get_plugin_repos_dir()
        if not os.path.isdir(base):
            return []
        for plugin_dir in os.listdir(base):
            full_dir = os.path.join(base, plugin_dir)
            mcp_config = os.path.join(full_dir, "mcp.json")
            if os.path.exists(mcp_config):
                try:
                    with open(mcp_config, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    configs.append({
                        "pluginId": plugin_dir,
                        "mcpConfig": data,
                        "pluginRoot": full_dir,
                    })
                except Exception:
                    pass
    except Exception:
        pass
    return configs


def merge_mcp_plugin_configs(
    base_config: Dict[str, Any],
    plugin_configs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge MCP plugin configs into a base config."""
    merged = dict(base_config)
    servers = dict(merged.get("mcpServers") or {})

    for plugin_cfg in plugin_configs:
        mcp_config = plugin_cfg.get("mcpConfig", {})
        plugin_servers = mcp_config.get("mcpServers") or {}
        for server_name, server_cfg in plugin_servers.items():
            if server_name not in servers:
                servers[server_name] = server_cfg

    merged["mcpServers"] = servers
    return merged
