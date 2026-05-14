"""Session cache clearing utilities. Ported from commands/clear/caches.ts"""
from __future__ import annotations

from typing import FrozenSet


def clear_session_caches(preserved_agent_ids: FrozenSet[str] = frozenset()) -> None:
    """Clear all session-related caches.

    Call this when resuming a session to ensure fresh file/skill discovery.
    This is a subset of what clear_conversation does - it only clears caches
    without affecting messages, session ID, or triggering hooks.

    Args:
        preserved_agent_ids: Agent IDs whose per-agent state should survive
            the clear (e.g., background tasks preserved across /clear).
    """
    has_preserved = len(preserved_agent_ids) > 0

    # Clear git/repository caches
    try:
        from claude_code.utils.git import clear_repository_caches  # type: ignore
        clear_repository_caches()
    except Exception:
        pass

    # Clear invoked skills cache
    try:
        from claude_code.bootstrap.state import clear_invoked_skills  # type: ignore
        clear_invoked_skills(preserved_agent_ids)
    except Exception:
        pass

    # Clear dynamic skills
    try:
        from claude_code.skills.registry import clear_dynamic_skills  # type: ignore
        clear_dynamic_skills()
    except Exception:
        pass

    # Clear bash command prefix caches
    try:
        from claude_code.utils.bash.commands import clear_command_prefix_caches  # type: ignore
        clear_command_prefix_caches()
    except Exception:
        pass

    # Clear memory files cache
    try:
        from claude_code.utils.claudemd import reset_get_memory_files_cache  # type: ignore
        reset_get_memory_files_cache("session_start")
    except Exception:
        pass

    # Clear swarm permission pending callbacks (unless preserving agents)
    if not has_preserved:
        try:
            from claude_code.utils.swarm.permission_sync import clear_all_pending_callbacks  # type: ignore
            clear_all_pending_callbacks()
        except Exception:
            pass

    # Clear LSP diagnostic state
    try:
        from claude_code.services.lsp.manager import reset_all_lsp_diagnostic_state  # type: ignore
        reset_all_lsp_diagnostic_state()
    except Exception:
        pass
