"""User-Agent string helpers. Ported from userAgent.ts"""
from __future__ import annotations
from claude_code import __version__

def get_claude_code_user_agent() -> str:
    return f"claude-code/{__version__}"
