"""MCP channel permissions. Ported from services/mcp/channelPermissions.ts"""
from __future__ import annotations
from typing import Dict, List

def get_channel_permissions(server_name: str, config: dict) -> Dict[str, bool]:
    return {"read": True, "write": True, "execute": True}
