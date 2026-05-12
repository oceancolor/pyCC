"""
skill_loaded_event.py - Skill loaded telemetry event.

Port of TypeScript skillLoadedEvent.ts.
"""

import time
from typing import Any, Dict, Optional


def log_skill_loaded_event(
    skill_name: str,
    skill_version: Optional[str] = None,
    load_duration_ms: Optional[float] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log a telemetry event when a skill is loaded.

    Args:
        skill_name: Name of the loaded skill
        skill_version: Version of the skill if available
        load_duration_ms: How long loading took
        attributes: Additional attributes to include
    """
    try:
        from ...services.analytics.index import log_event

        event_attrs: Dict[str, Any] = {
            'skillName': skill_name,
        }

        if skill_version:
            event_attrs['skillVersion'] = skill_version

        if load_duration_ms is not None:
            event_attrs['loadDurationMs'] = load_duration_ms

        if attributes:
            event_attrs.update(attributes)

        log_event('tengu_skill_loaded', event_attrs)
    except ImportError:
        # Analytics not available
        pass


def log_skills_summary_event(
    skills: list,
    total_load_duration_ms: Optional[float] = None,
) -> None:
    """
    Log a summary event of all loaded skills.

    Args:
        skills: List of skill info dicts with 'name' and optional 'version' keys
        total_load_duration_ms: Total time to load all skills
    """
    try:
        from ...services.analytics.index import log_event

        attrs: Dict[str, Any] = {
            'skillCount': len(skills),
            'skillNames': ','.join(s.get('name', '') for s in skills),
        }

        if total_load_duration_ms is not None:
            attrs['totalLoadDurationMs'] = total_load_duration_ms

        log_event('tengu_skills_summary', attrs)
    except ImportError:
        pass
