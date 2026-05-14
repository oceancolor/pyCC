"""Post-compact cleanup. Ported from services/compact/postCompactCleanup.ts"""
from __future__ import annotations
from typing import Optional


def run_post_compact_cleanup(query_source: Optional[str] = None) -> None:
    """Run cleanup of caches and tracking state after compaction.

    Call this after both auto-compact and manual /compact to free memory
    held by tracking structures that are invalidated by compaction.

    Note: Does NOT clear invoked skill content — skill content must survive
    across multiple compactions so that createSkillAttachmentIfNeeded() can
    include the full skill text in subsequent compaction attachments.

    Args:
        query_source: The compacting query's source. Only reset main-thread
            module-level state for main-thread compacts (not subagents).
    """
    # Determine if this is a main-thread compact
    is_main_thread_compact = (
        query_source is None
        or query_source.startswith("repl_main_thread")
        or query_source == "sdk"
    )

    # Reset micro-compact state
    try:
        from claude_code.services.compact.micro_compact import reset_microcompact_state
        reset_microcompact_state()
    except Exception:
        pass

    if is_main_thread_compact:
        # Reset memory files cache
        try:
            from claude_code.utils.claudemd import reset_get_memory_files_cache
            reset_get_memory_files_cache()
        except Exception:
            pass

        # Reset user context cache
        try:
            from claude_code.context import reset_user_context_cache
            reset_user_context_cache()
        except Exception:
            pass

    # Clear session messages cache (safe for both main and subagent)
    try:
        from claude_code.utils.session_storage import clear_session_messages_cache
        clear_session_messages_cache()
    except Exception:
        pass

    # Clear speculative checks
    try:
        from claude_code.tools.bash_tool.bash_permissions import clear_speculative_checks
        clear_speculative_checks()
    except Exception:
        pass

    # Clear classifier approvals
    try:
        from claude_code.utils.classifier_approvals import clear_classifier_approvals
        clear_classifier_approvals()
    except Exception:
        pass

    # Clear system prompt sections cache
    try:
        from claude_code.constants.system_prompt_sections import clear_system_prompt_sections
        clear_system_prompt_sections()
    except Exception:
        pass
