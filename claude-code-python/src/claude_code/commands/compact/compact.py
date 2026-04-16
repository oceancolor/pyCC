"""
Ported from: commands/compact/compact.ts (287 lines)

Full /compact command implementation. Handles:
- Session-memory compaction (fast path, no custom instructions)
- Reactive-only mode routing
- Traditional compaction via microcompact → compactConversation
- Full error handling and cleanup

React/Ink UI components (onCompactProgress, setStreamMode, etc.) are
omitted — only the business-logic / data layer is ported.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Feature flags
REACTIVE_COMPACT_ENABLED: bool = os.environ.get("REACTIVE_COMPACT", "").lower() in ("1", "true", "yes")
PROMPT_CACHE_BREAK_DETECTION: bool = os.environ.get("PROMPT_CACHE_BREAK_DETECTION", "").lower() in ("1", "true", "yes")

# Error messages (mirrors TS constants)
ERROR_MESSAGE_NOT_ENOUGH_MESSAGES = "Not enough messages to compact"
ERROR_MESSAGE_INCOMPLETE_RESPONSE = "Incomplete response from compaction model"
ERROR_MESSAGE_USER_ABORT = "User aborted compaction"


class CompactionResult:
    """Result of a successful compaction operation."""
    def __init__(
        self,
        messages: List[Any],
        summary: str = "",
        user_display_message: Optional[str] = None,
    ) -> None:
        self.messages = messages
        self.summary = summary
        self.user_display_message = user_display_message


class CompactCallResult:
    """Return type for the compact call() entrypoint."""
    def __init__(
        self,
        type: str,
        compaction_result: CompactionResult,
        display_text: str,
    ) -> None:
        self.type = type
        self.compaction_result = compaction_result
        self.display_text = display_text


def _has_exact_error_message(error: Exception, message: str) -> bool:
    return str(error).strip() == message.strip()


def _build_display_text(
    context: Any,
    user_display_message: Optional[str] = None,
) -> str:
    """
    Build the dimmed display text shown after compaction.
    Mirrors buildDisplayText() — omits chalk.dim (terminal-specific).
    """
    parts: List[str] = []
    options = getattr(context, "options", None)
    verbose = getattr(options, "verbose", False) if options else False
    if not verbose:
        parts.append("(ctrl+o to see full summary)")
    if user_display_message:
        parts.append(user_display_message)
    return "Compacted " + "\n".join(parts)


async def _get_messages_after_compact_boundary(messages: List[Any]) -> List[Any]:
    try:
        from claude_code.utils.messages import get_messages_after_compact_boundary
        return get_messages_after_compact_boundary(messages)
    except ImportError:
        return messages


async def _run_microcompact(messages: List[Any], context: Any = None) -> List[Any]:
    try:
        from claude_code.services.compact.micro_compact import microcompact_messages
        result = await microcompact_messages(messages, context=context)
        if isinstance(result, dict):
            return result.get("messages", messages)
        return result
    except (ImportError, Exception):
        return messages


async def _try_session_memory_compaction(
    messages: List[Any],
    agent_id: Optional[str],
) -> Optional[CompactionResult]:
    try:
        from claude_code.services.compact.session_memory_compact import try_session_memory_compaction
        return await try_session_memory_compaction(messages, agent_id)
    except (ImportError, Exception):
        return None


async def _compact_conversation(
    messages: List[Any],
    context: Any,
    custom_instructions: str,
) -> CompactionResult:
    try:
        from claude_code.services.compact.compact import compact_conversation
        result = await compact_conversation(
            messages,
            context=context,
            custom_instructions=custom_instructions or None,
        )
        if isinstance(result, CompactionResult):
            return result
        if isinstance(result, dict):
            return CompactionResult(
                messages=result.get("messages", messages),
                summary=result.get("summary", ""),
                user_display_message=result.get("user_display_message"),
            )
        return CompactionResult(messages=messages, summary="")
    except (ImportError, Exception) as e:
        raise RuntimeError(f"{ERROR_MESSAGE_INCOMPLETE_RESPONSE}: {e}") from e


async def call(args: str, context: Any = None) -> CompactCallResult:
    """
    Entry point for the /compact slash command.
    Mirrors call() from compact.ts with the full compaction pipeline.
    """
    messages: List[Any] = getattr(context, "messages", []) if context else []
    abort_controller = getattr(context, "abort_controller", None)
    agent_id: Optional[str] = getattr(context, "agent_id", None)

    # Slice to post-compact-boundary (REPL keeps snipped messages for scrollback)
    messages = await _get_messages_after_compact_boundary(messages)

    if not messages:
        raise ValueError("No messages to compact")

    custom_instructions: str = (args or "").strip()

    try:
        # --- Fast path: session-memory compaction (no custom instructions) ---
        if not custom_instructions:
            session_result = await _try_session_memory_compaction(messages, agent_id)
            if session_result is not None:
                # Post-compact cleanup
                try:
                    from claude_code.services.compact.post_compact_cleanup import run_post_compact_cleanup
                    run_post_compact_cleanup()
                except ImportError:
                    pass

                try:
                    from claude_code.services.SessionMemory.session_memory_utils import set_last_summarized_message_id
                    set_last_summarized_message_id(None)
                except ImportError:
                    pass

                if PROMPT_CACHE_BREAK_DETECTION:
                    try:
                        from claude_code.services.api.prompt_cache_break_detection import notify_compaction
                        source = getattr(getattr(context, "options", None), "query_source", "compact") or "compact"
                        notify_compaction(source, agent_id)
                    except ImportError:
                        pass

                return CompactCallResult(
                    type="compact",
                    compaction_result=session_result,
                    display_text=_build_display_text(context),
                )

        # --- Reactive-only mode ---
        if REACTIVE_COMPACT_ENABLED:
            try:
                from claude_code.services.compact.reactive_compact import (
                    is_reactive_only_mode,
                    reactive_compact_on_prompt_too_long,
                )
                if is_reactive_only_mode():
                    return await _compact_via_reactive(
                        messages, context, custom_instructions,
                        reactive_compact_on_prompt_too_long,
                    )
            except ImportError:
                pass

        # --- Traditional compaction path ---
        microcompacted = await _run_microcompact(messages, context)
        result = await _compact_conversation(microcompacted, context, custom_instructions)

        # Reset last summarized message id (legacy compaction replaces all messages)
        try:
            from claude_code.services.SessionMemory.session_memory_utils import set_last_summarized_message_id
            set_last_summarized_message_id(None)
        except ImportError:
            pass

        # Suppress compact warning
        try:
            from claude_code.services.compact.compact_warning_state import suppress_compact_warning
            suppress_compact_warning()
        except ImportError:
            pass

        try:
            from claude_code.services.compact.post_compact_cleanup import run_post_compact_cleanup
            run_post_compact_cleanup()
        except ImportError:
            pass

        return CompactCallResult(
            type="compact",
            compaction_result=result,
            display_text=_build_display_text(context, result.user_display_message),
        )

    except Exception as error:
        # Check if aborted
        if abort_controller is not None:
            signal = getattr(abort_controller, "signal", None)
            aborted = getattr(signal, "aborted", False) if signal else False
            if aborted:
                raise RuntimeError("Compaction canceled.") from error

        if _has_exact_error_message(error, ERROR_MESSAGE_NOT_ENOUGH_MESSAGES):
            raise RuntimeError(ERROR_MESSAGE_NOT_ENOUGH_MESSAGES) from error
        elif _has_exact_error_message(error, ERROR_MESSAGE_INCOMPLETE_RESPONSE):
            raise RuntimeError(ERROR_MESSAGE_INCOMPLETE_RESPONSE) from error
        else:
            raise RuntimeError(f"Error during compaction: {error}") from error


async def _compact_via_reactive(
    messages: List[Any],
    context: Any,
    custom_instructions: str,
    reactive_compact_fn: Any,
) -> CompactCallResult:
    """
    Route /compact through the reactive compaction path.
    Mirrors compactViaReactive() from the TS source.
    """
    try:
        from claude_code.utils.hooks import execute_pre_compact_hooks
        abort_signal = None
        abort_controller = getattr(context, "abort_controller", None)
        if abort_controller:
            abort_signal = getattr(abort_controller, "signal", None)

        hook_result = await execute_pre_compact_hooks(
            {"trigger": "manual", "custom_instructions": custom_instructions or None},
            abort_signal,
        )
    except ImportError:
        hook_result = type("HookResult", (), {"user_display_message": None, "new_custom_instructions": None})()

    merged_instructions = custom_instructions
    new_custom = getattr(hook_result, "new_custom_instructions", None)
    if new_custom:
        merged_instructions = "\n".join(filter(None, [custom_instructions, new_custom]))

    outcome = await reactive_compact_fn(
        messages,
        {},  # cache params stub
        {"custom_instructions": merged_instructions, "trigger": "manual"},
    )

    ok = getattr(outcome, "ok", False)
    if not ok:
        reason = getattr(outcome, "reason", "error")
        if reason == "too_few_groups":
            raise RuntimeError(ERROR_MESSAGE_NOT_ENOUGH_MESSAGES)
        elif reason == "aborted":
            raise RuntimeError(ERROR_MESSAGE_USER_ABORT)
        else:
            raise RuntimeError(ERROR_MESSAGE_INCOMPLETE_RESPONSE)

    outcome_result = getattr(outcome, "result", None)
    if outcome_result is None:
        outcome_result = CompactionResult(messages=messages)

    # Post-success cleanup
    try:
        from claude_code.services.SessionMemory.session_memory_utils import set_last_summarized_message_id
        set_last_summarized_message_id(None)
    except ImportError:
        pass

    try:
        from claude_code.services.compact.post_compact_cleanup import run_post_compact_cleanup
        run_post_compact_cleanup()
    except ImportError:
        pass

    try:
        from claude_code.services.compact.compact_warning_state import suppress_compact_warning
        suppress_compact_warning()
    except ImportError:
        pass

    hook_msg = getattr(hook_result, "user_display_message", None)
    result_msg = getattr(outcome_result, "user_display_message", None)
    combined = "\n".join(m for m in [hook_msg, result_msg] if m) or None

    if isinstance(outcome_result, CompactionResult):
        compaction_result = CompactionResult(
            messages=outcome_result.messages,
            summary=outcome_result.summary,
            user_display_message=combined,
        )
    else:
        compaction_result = CompactionResult(messages=messages, user_display_message=combined)

    return CompactCallResult(
        type="compact",
        compaction_result=compaction_result,
        display_text=_build_display_text(context, combined),
    )
