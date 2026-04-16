"""MCP config normalization. Ported from services/mcp/normalization.ts"""
from __future__ import annotations
from typing import Any, Dict


def normalize_mcp_server_name(name: str) -> str:
    return name.strip().replace(" ", "_").lower()


def normalize_mcp_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {normalize_mcp_server_name(k): v for k, v in config.items()}
