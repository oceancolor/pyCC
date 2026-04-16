"""Claude AI limits hook stub. Ported from services/claudeAiLimitsHook.ts (React hook → stub)"""
from __future__ import annotations
from claude_code.services.claude_ai_limits import get_current_limits, ClaudeAILimits


def use_claude_ai_limits() -> ClaudeAILimits:
    """Stub: return current limits snapshot (no React reactivity in Python)."""
    return get_current_limits()
