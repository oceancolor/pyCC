"""
Register frontmatter hooks - registers hooks from agent/skill frontmatter into session-scoped hooks.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def register_frontmatter_hooks(
    set_app_state: Any,
    session_id: str,
    hooks: Dict[str, Any],
    source_name: str,
    is_agent: bool = False,
) -> None:
    """Register hooks from frontmatter into session-scoped hooks."""
    from .session_hooks import add_session_hook
    from ..log import log_for_debugging
    from .hook_events import HOOK_EVENTS

    if not hooks or not hooks.keys():
        return

    hook_count = 0

    for event in HOOK_EVENTS:
        matchers = hooks.get(event)
        if not matchers:
            continue

        # For agents, convert Stop hooks to SubagentStop
        target_event = event
        if is_agent and event == "Stop":
            target_event = "SubagentStop"
            log_for_debugging(
                f"Converting Stop hook to SubagentStop for {source_name} (subagents trigger SubagentStop)"
            )

        for matcher_config in matchers:
            if isinstance(matcher_config, dict):
                matcher = matcher_config.get("matcher") or ""
                hooks_array = matcher_config.get("hooks", [])
            else:
                continue

            if not hooks_array:
                continue

            for hook in hooks_array:
                add_session_hook(set_app_state, session_id, target_event, matcher, hook)
                hook_count += 1

    if hook_count > 0:
        log_for_debugging(
            f"Registered {hook_count} frontmatter hook(s) from {source_name} for session {session_id}"
        )
