"""
Load plugin commands - loads slash commands from installed plugins.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def load_plugin_commands(plugin_dir: str) -> List[Dict[str, Any]]:
    """Load slash command definitions from a plugin directory."""
    commands: List[Dict[str, Any]] = []
    commands_dir = os.path.join(plugin_dir, "commands")
    if not os.path.isdir(commands_dir):
        return commands

    for filename in os.listdir(commands_dir):
        if not (filename.endswith(".md") or filename.endswith(".json")):
            continue
        path = os.path.join(commands_dir, filename)
        try:
            if filename.endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    cmd = json.load(f)
                commands.append(cmd)
            else:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                cmd_name = filename[:-3]
                commands.append({"name": cmd_name, "content": content, "path": path})
        except Exception:
            pass

    return commands


def load_all_plugins_commands(
    plugin_dirs: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Load commands from all installed plugin directories."""
    from .plugin_directories import get_plugin_repos_dir
    base = get_plugin_repos_dir()
    if not os.path.isdir(base):
        return []

    dirs = plugin_dirs or [
        os.path.join(base, d) for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    ]

    commands: List[Dict[str, Any]] = []
    for d in dirs:
        commands.extend(load_plugin_commands(d))
    return commands
