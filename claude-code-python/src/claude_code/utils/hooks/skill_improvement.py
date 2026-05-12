"""
Skill improvement - post-sampling hook for analyzing and improving skills.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def register_skill_improvement_hook() -> None:
    """Register the skill improvement post-sampling hook."""
    from .post_sampling_hooks import register_post_sampling_hook

    async def skill_improvement_hook(context: Dict[str, Any]) -> None:
        # Skill improvement is an advanced ANT-only feature.
        # In the Python port, this is a stub that does nothing.
        pass

    register_post_sampling_hook(skill_improvement_hook)
