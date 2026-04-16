"""MCP channel allowlist. Ported from services/mcp/channelAllowlist.ts"""
from __future__ import annotations
from typing import List

BUILTIN_ALLOWED_CHANNELS: List[str] = []

def is_channel_allowed(channel: str, allowlist: List[str]) -> bool:
    return channel in allowlist or channel in BUILTIN_ALLOWED_CHANNELS
