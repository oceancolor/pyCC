"""MCP official server registry. Ported from services/mcp/officialRegistry.ts"""
from __future__ import annotations
from typing import Dict, Optional

OFFICIAL_MCP_REGISTRY: Dict[str, dict] = {}

def get_official_server(server_name: str) -> Optional[dict]:
    return OFFICIAL_MCP_REGISTRY.get(server_name)
