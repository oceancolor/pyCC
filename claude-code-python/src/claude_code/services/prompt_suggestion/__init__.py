"""Prompt suggestion module exports.

Ported from services/PromptSuggestion/.
"""
from claude_code.services.prompt_suggestion.prompt_suggestion import (
    PromptVariant,
    get_prompt_suggestions,
    get_prompt_variant,
    should_enable_prompt_suggestion,
    abort_prompt_suggestion,
    get_suggestion_suppress_reason,
    should_filter_suggestion,
    log_suggestion_suppressed,
    log_suggestion_outcome,
)
from claude_code.services.prompt_suggestion.speculation import (
    SpeculationState,
    SpeculationStatus,
    is_speculation_enabled,
    prepare_messages_for_injection,
    start_speculation,
    accept_speculation,
    abort_speculation,
    handle_speculation_accept,
    speculate,
)

__all__ = [
    # prompt_suggestion
    "PromptVariant",
    "get_prompt_suggestions",
    "get_prompt_variant",
    "should_enable_prompt_suggestion",
    "abort_prompt_suggestion",
    "get_suggestion_suppress_reason",
    "should_filter_suggestion",
    "log_suggestion_suppressed",
    "log_suggestion_outcome",
    # speculation
    "SpeculationState",
    "SpeculationStatus",
    "is_speculation_enabled",
    "prepare_messages_for_injection",
    "start_speculation",
    "accept_speculation",
    "abort_speculation",
    "handle_speculation_accept",
    "speculate",
]
