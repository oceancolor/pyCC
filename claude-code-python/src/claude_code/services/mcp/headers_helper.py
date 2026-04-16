"""MCP headers helper. Ported from services/mcp/headersHelper.ts"""
from __future__ import annotations
import os
from typing import Dict

def build_default_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    token = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
