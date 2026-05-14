"""Skill improvement - post-sampling hook for analyzing and improving skills.

Ported from hooks/skillImprovement.ts (inferred from context).
This hook fires after each model response and looks for opportunities to
improve the agent's skills based on what tools were used, what succeeded,
and what failed.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

_LOG = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Hook registration                                                            #
# --------------------------------------------------------------------------- #


async def _default_skill_improvement_hook(context: Dict[str, Any]) -> None:
    """Analyse tool results and update skill usage statistics.

    This is an advanced ANT-only feature. In the Python port we implement
    the bookkeeping portion only (no LLM-based skill rewriting).

    Args:
        context: Post-sampling hook context with keys like ``tool_results``,
                 ``conversation_id``, ``turn_count``, etc.
    """
    tool_results: List[Dict[str, Any]] = context.get("tool_results", [])
    if not tool_results:
        return

    # Record success/failure counts per tool for metrics
    success_count = sum(
        1 for r in tool_results if r.get("status") == "success"
    )
    failure_count = len(tool_results) - success_count

    if failure_count > 0:
        _LOG.debug(
            "Skill improvement hook: %d/%d tool calls failed in this turn",
            failure_count,
            len(tool_results),
        )

    # Future: Call skills_utils.record_tool_usage() per tool result
    # so that the decay-based ranking stays up to date.
    try:
        from claude_code.utils.skills.skills_utils import record_tool_usage

        for result in tool_results:
            tool_name: Optional[str] = result.get("tool_name") or result.get("name")
            if tool_name:
                success = result.get("status") == "success"
                await record_tool_usage(tool_name, success=success)
    except ImportError:
        pass
    except Exception as exc:
        _LOG.debug("Skill improvement hook: record_tool_usage failed: %s", exc)


def register_skill_improvement_hook() -> None:
    """Register the skill improvement post-sampling hook.

    The hook is idempotent; calling this more than once has no effect.
    """
    try:
        from .post_sampling_hooks import register_post_sampling_hook

        register_post_sampling_hook(_default_skill_improvement_hook)
    except ImportError:
        _LOG.debug(
            "post_sampling_hooks module not available; "
            "skill improvement hook not registered"
        )
