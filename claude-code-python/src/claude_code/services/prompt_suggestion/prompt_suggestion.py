"""Prompt suggestion service.

Ported from services/PromptSuggestion/promptSuggestion.ts

Provides helpers to decide whether to generate prompt suggestions (a.k.a.
"intent clarification" proposals) and to execute the speculative generation
pipeline.  In this Python port most of the React-state machinery is omitted;
we expose the pure logic functions that are testable in isolation.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Literal, Optional

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PromptVariant = Literal["user_intent", "stated_intent"]

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

_ENABLE_ENV = "CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION"


def get_prompt_variant() -> PromptVariant:
    """Return the active prompt variant (always 'user_intent' in current impl)."""
    return "user_intent"


def should_enable_prompt_suggestion() -> bool:
    """Decide whether prompt suggestions are enabled for this session.

    Mirrors the TypeScript ``shouldEnablePromptSuggestion`` logic without the
    GrowthBook / React dependencies.  The environment variable acts as an
    override for testing.
    """
    env_val = os.environ.get(_ENABLE_ENV, "").strip().lower()
    if env_val in ("0", "false", "no", "off"):
        return False
    if env_val in ("1", "true", "yes", "on"):
        return True
    # Default: disabled (GrowthBook feature flag defaults to false)
    return False


def abort_prompt_suggestion(abort_controller: Any = None) -> None:
    """Abort any in-flight prompt suggestion request."""
    if abort_controller is not None and hasattr(abort_controller, "abort"):
        abort_controller.abort()


def get_suggestion_suppress_reason(app_state: Dict[str, Any]) -> Optional[str]:
    """Return a reason string if suggestions should be suppressed, else None.

    Args:
        app_state: A dict representing the current application state.
    """
    if not app_state.get("prompt_suggestion_enabled", True):
        return "disabled"
    if app_state.get("pending_worker_request") or app_state.get("pending_sandbox_request"):
        return "pending_permission"
    if app_state.get("elicitation_queue"):
        return "elicitation_active"
    if app_state.get("tool_permission_mode") == "plan":
        return "plan_mode"
    return None


def should_filter_suggestion(suggestion: str, original_input: str) -> bool:
    """Return True if the generated suggestion should be discarded.

    Mirrors the TypeScript ``shouldFilterSuggestion`` heuristics.
    """
    if not suggestion or not suggestion.strip():
        return True
    # Reject if essentially identical to the original
    if suggestion.strip().lower() == original_input.strip().lower():
        return True
    return False


def log_suggestion_suppressed(reason: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """Log that suggestion generation was suppressed (no-op in Python port)."""
    pass  # Analytics logging would go here


def log_suggestion_outcome(
    outcome: str,
    suggestion: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Log the outcome of a suggestion generation attempt (no-op in Python port)."""
    pass  # Analytics logging would go here


# ---------------------------------------------------------------------------
# Public API (backward-compat alias used by __init__.py)
# ---------------------------------------------------------------------------

def get_prompt_suggestions(partial_input: str, context: Dict[str, Any]) -> List[str]:
    """Return prompt suggestions for *partial_input* given *context*.

    This is a lightweight synchronous wrapper kept for backward compatibility.
    Real suggestion generation is async (see speculation.py).
    """
    if not should_enable_prompt_suggestion():
        return []
    if not partial_input or not partial_input.strip():
        return []
    return []
