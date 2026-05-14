"""Tip registry. Ported from services/tips/tipRegistry.ts"""
from __future__ import annotations
import math
from typing import Any, Callable, Dict, List, Optional


class Tip:
    """A displayable hint/tip shown to the user on startup."""

    def __init__(
        self,
        tip_id: str,
        content: Callable,
        cooldown_sessions: int = 0,
        is_relevant: Optional[Callable] = None,
    ) -> None:
        self.id = tip_id
        self.content = content
        self.cooldown_sessions = cooldown_sessions
        self._is_relevant = is_relevant or (lambda ctx=None: True)

    async def get_content(self, context: Any = None) -> str:
        import asyncio
        result = self.content(context) if callable(self.content) else self.content
        if asyncio.iscoroutine(result):
            result = await result
        return str(result)

    async def is_relevant(self, context: Any = None) -> bool:
        import asyncio
        result = self._is_relevant(context) if callable(self._is_relevant) else self._is_relevant
        if asyncio.iscoroutine(result):
            result = await result
        return bool(result)


async def get_relevant_tips(context: Any = None) -> List[Tip]:
    """Return tips that are relevant and whose cooldown has elapsed."""
    from claude_code.services.tips.tip_history import get_sessions_since_last_shown

    tips = _get_all_builtin_tips()

    relevant: List[Tip] = []
    for tip in tips:
        try:
            if not await tip.is_relevant(context):
                continue
            if get_sessions_since_last_shown(tip.id) < tip.cooldown_sessions:
                continue
            relevant.append(tip)
        except Exception:
            pass

    return relevant


def _get_all_builtin_tips() -> List[Tip]:
    """Return all built-in tips."""
    return [
        Tip(
            "continue",
            lambda ctx=None: "Run claude --continue or claude --resume to resume a conversation",
            cooldown_sessions=10,
        ),
        Tip(
            "shift-tab",
            lambda ctx=None: "Hit Shift+Tab to cycle between default mode, auto-accept edit mode, and plan mode",
            cooldown_sessions=10,
        ),
        Tip(
            "memory-command",
            lambda ctx=None: "Use /memory to view and manage Claude memory",
            cooldown_sessions=15,
        ),
        Tip(
            "permissions",
            lambda ctx=None: "Use /permissions to pre-approve and pre-deny bash, edit, and MCP tools",
            cooldown_sessions=10,
        ),
        Tip(
            "custom-commands",
            lambda ctx=None: "Create skills by adding .md files to .claude/skills/ in your project",
            cooldown_sessions=15,
        ),
    ]


def get_all_tips() -> List[Tip]:
    """Return all registered tips."""
    return _get_all_builtin_tips()
