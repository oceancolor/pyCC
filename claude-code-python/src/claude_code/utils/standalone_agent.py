"""Standalone agent utilities. Ported from standaloneAgent.ts"""
from __future__ import annotations
from typing import Any, Optional

def get_standalone_agent_name(app_state: Any) -> Optional[str]:
    from claude_code.utils.teammate import get_team_name
    if get_team_name():
        return None
    ctx = getattr(app_state, 'standalone_agent_context', None)
    return ctx.get('name') if isinstance(ctx, dict) else getattr(ctx, 'name', None)
