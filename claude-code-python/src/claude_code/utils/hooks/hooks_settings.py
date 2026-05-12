"""
Hooks settings - get and manage hooks from various sources.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_all_hooks(app_state: Any) -> List[Dict[str, Any]]:
    """Get all hooks from all allowed sources."""
    return []


def get_hooks_for_event(app_state: Any, event: str) -> List[Dict[str, Any]]:
    """Get hooks for a specific event."""
    return [h for h in get_all_hooks(app_state) if h.get("event") == event]


def sort_matchers_by_priority(
    matchers: List[str],
    hooks_by_event_and_matcher: Dict[str, Dict[str, List[Any]]],
    selected_event: str,
) -> List[str]:
    """Sort matchers by priority based on their sources."""
    SOURCE_PRIORITY = {
        "userSettings": 0,
        "projectSettings": 1,
        "localSettings": 2,
    }

    def get_source_priority(source: str) -> int:
        if source in ("pluginHook", "builtinHook"):
            return 999
        return SOURCE_PRIORITY.get(source, 500)

    def min_priority(matcher: str) -> int:
        hooks = hooks_by_event_and_matcher.get(selected_event, {}).get(matcher, [])
        sources = list({h.get("source", "") for h in hooks})
        if not sources:
            return 999
        return min(get_source_priority(s) for s in sources)

    return sorted(matchers, key=lambda m: (min_priority(m), m))
