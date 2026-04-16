"""MCP env var expansion. Ported from services/mcp/envExpansion.ts"""
from __future__ import annotations
import os
from typing import Dict


def expand_env_vars(env: Dict[str, str]) -> Dict[str, str]:
    return {k: os.path.expandvars(v) for k, v in env.items()}
