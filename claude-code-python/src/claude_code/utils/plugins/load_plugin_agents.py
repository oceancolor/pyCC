"""
Load plugin agents - loads agent definitions from installed plugins.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def load_plugin_agents(plugin_dir: str) -> List[Dict[str, Any]]:
    """Load agent definitions from a plugin directory."""
    agents: List[Dict[str, Any]] = []
    agents_dir = os.path.join(plugin_dir, "agents")
    if not os.path.isdir(agents_dir):
        return agents

    for filename in os.listdir(agents_dir):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(agents_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            agent_id = filename[:-3]
            agents.append({
                "id": agent_id,
                "path": path,
                "content": content,
            })
        except Exception:
            pass

    return agents


def load_all_plugins_agents(
    plugin_dirs: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Load agents from all installed plugin directories."""
    from .plugin_directories import get_plugin_repos_dir
    base = get_plugin_repos_dir()
    if not os.path.isdir(base):
        return []

    dirs = plugin_dirs or [
        os.path.join(base, d) for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    ]

    agents: List[Dict[str, Any]] = []
    for d in dirs:
        agents.extend(load_plugin_agents(d))
    return agents
