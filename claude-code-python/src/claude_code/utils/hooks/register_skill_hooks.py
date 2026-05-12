"""
Register skill hooks - registers hooks from a skill's frontmatter as session hooks.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def register_skill_hooks(
    set_app_state: Any,
    session_id: str,
    hooks: Dict[str, Any],
    skill_name: str,
    skill_root: Optional[str] = None,
) -> None:
    """Register hooks from a skill's frontmatter as session hooks."""
    from .session_hooks import add_session_hook, remove_session_hook
    from ..log import log_for_debugging
    from .hook_events import HOOK_EVENTS

    registered_count = 0

    for event_name in HOOK_EVENTS:
        matchers = hooks.get(event_name)
        if not matchers:
            continue

        for matcher in matchers:
            if not isinstance(matcher, dict):
                continue
            matcher_str = matcher.get("matcher") or ""
            hooks_list = matcher.get("hooks", [])

            for hook in hooks_list:
                if not isinstance(hook, dict):
                    continue

                # For once: true hooks, use onHookSuccess callback to remove after execution
                on_hook_success = None
                if hook.get("once"):
                    captured_hook = dict(hook)

                    def make_on_success(h):
                        def on_success(_hook, _result):
                            log_for_debugging(
                                f"Removing one-shot hook for event {event_name} in skill '{skill_name}'"
                            )
                            remove_session_hook(set_app_state, session_id, event_name, h)
                        return on_success

                    on_hook_success = make_on_success(captured_hook)

                add_session_hook(
                    set_app_state,
                    session_id,
                    event_name,
                    matcher_str,
                    hook,
                    on_hook_success,
                    skill_root,
                )
                registered_count += 1

    if registered_count > 0:
        log_for_debugging(f"Registered {registered_count} hooks from skill '{skill_name}'")
