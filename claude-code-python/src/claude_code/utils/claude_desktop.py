"""Claude Desktop integration utilities. Ported from utils/claudeDesktop.ts"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Optional


def get_claude_desktop_config_path() -> Optional[str]:
    """Get the Claude Desktop config path for the current platform."""
    if sys.platform == "darwin":
        return str(Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return os.path.join(appdata, "Claude", "claude_desktop_config.json") if appdata else None
    else:
        # Linux/WSL: try typical Windows path via /mnt/c
        userprofile = os.environ.get("USERPROFILE", "").replace("\\", "/")
        if userprofile:
            wsl_path = userprofile.replace("/C:", "/mnt/c")
            return f"{wsl_path}/AppData/Roaming/Claude/claude_desktop_config.json"
    return None


async def get_claude_desktop_mcp_servers() -> dict:
    """Read MCP server configs from Claude Desktop config file."""
    config_path = get_claude_desktop_config_path()
    if not config_path:
        return {}
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        return cfg.get("mcpServers", {})
    except Exception:
        return {}
