"""
Ported from: commands/cost/cost.ts

/cost command — display the total cost for the current session.
For Claude.ai subscriber accounts the response is different (shows
subscription notice rather than raw cost), matching the TS behaviour.
"""
from __future__ import annotations

from typing import Dict


# ---------------------------------------------------------------------------
# Stub helpers — real implementations live in utils/auth and cost_tracker
# ---------------------------------------------------------------------------

def _is_claude_ai_subscriber() -> bool:
    try:
        from claude_code.utils.auth import is_claude_ai_subscriber  # type: ignore[import]
        return is_claude_ai_subscriber()
    except ImportError:
        return False


def _format_total_cost() -> str:
    try:
        from claude_code.cost_tracker import format_total_cost  # type: ignore[import]
        return format_total_cost()
    except ImportError:
        return "Cost tracking not available."


def _get_current_limits() -> object:
    try:
        from claude_code.services.claude_ai_limits import current_limits  # type: ignore[import]
        return current_limits
    except ImportError:
        return None


def _is_using_overage(limits: object) -> bool:
    if limits is None:
        return False
    return bool(getattr(limits, "is_using_overage", False))


def _is_ant_user() -> bool:
    import os
    return os.environ.get("USER_TYPE") == "ant"


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call() -> Dict[str, str]:
    """
    Return the current session cost as a text result dict.

    Returns
    -------
    dict
        ``{"type": "text", "value": <message>}``  —  matches LocalCommandResult.
    """
    if _is_claude_ai_subscriber():
        limits = _get_current_limits()

        if _is_using_overage(limits):
            value = (
                "You are currently using your overages to power your Claude Code usage. "
                "We will automatically switch you back to your subscription rate limits "
                "when they reset"
            )
        else:
            value = (
                "You are currently using your subscription to power your Claude Code usage"
            )

        # ANT employees see the cost anyway
        if _is_ant_user():
            value += f"\n\n[ANT-ONLY] Showing cost anyway:\n {_format_total_cost()}"

        return {"type": "text", "value": value}

    return {"type": "text", "value": _format_total_cost()}
