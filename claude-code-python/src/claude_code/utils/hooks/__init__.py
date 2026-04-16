"""
hooks/__init__.py — Public facade for the hooks subsystem.

This package re-exports every public symbol from the three implementation
sub-modules so callers can always do::

    from claude_code.utils.hooks import execute_pre_tool_hooks, HookResult, ...

The implementation is split across:
  - hooks_types.py   – TypedDict / dataclass / Protocol type definitions
  - hooks_core.py    – low-level helpers (trust check, base-input builder,
                       query/matching utilities, message formatters)
  - hooks_execute.py – async hook execution engine and all execute_* functions

NOTE: The ``hooks/`` directory takes precedence over the sibling ``hooks.py``
file.  This ``__init__.py`` is the actual entry-point for all imports from
``claude_code.utils.hooks``.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Types (from hooks_types.py)
# ---------------------------------------------------------------------------
from claude_code.utils.hooks_types import (
    TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    SESSION_END_HOOK_TIMEOUT_MS_DEFAULT,
    # Hook event name enumerations
    HookEvent,
    HookEventName,
    ExtendedHookEvent,
    # Base / union input types
    BaseHookInput,
    HookInput,
    # Per-event input types
    PreToolUseHookInput,
    PostToolUseHookInput,
    PostToolUseFailureHookInput,
    PermissionDeniedHookInput,
    PermissionRequestHookInput,
    NotificationHookInput,
    SessionStartHookInput,
    SessionEndHookInput,
    SetupHookInput,
    StopHookInput,
    StopFailureHookInput,
    SubagentStartHookInput,
    SubagentStopHookInput,
    TeammateIdleHookInput,
    TaskCreatedHookInput,
    TaskCompletedHookInput,
    ConfigChangeHookInput,
    CwdChangedHookInput,
    FileChangedHookInput,
    InstructionsLoadedHookInput,
    UserPromptSubmitHookInput,
    ElicitationHookInput,
    ElicitationResultHookInput,
    PreCompactHookInput,
    PostCompactHookInput,
    # JSON output types
    SyncHookJSONOutput,
    AsyncHookJSONOutput,
    HookJSONOutput,
    HookSpecificOutput,
    # Hook definition types
    HookCommand,
    HookCallback,
    FunctionHook,
    MatchedHook,
    # Result types
    HookResult,
    AggregatedHookResult,
    HookResultMessage,
    HookBlockingError,
    ElicitationResponse,
    # Permission types
    PermissionBehavior,
    PermissionUpdate,
    PermissionRequestResult,
    PermissionRequestResultAllow,
    PermissionRequestResultDeny,
    # Misc
    ExitReason,
    # Type predicates
    is_async_hook_json_output,
    is_sync_hook_json_output,
)

# ---------------------------------------------------------------------------
# Core helpers (from hooks_core.py)
# ---------------------------------------------------------------------------
from claude_code.utils.hooks_core import (
    get_session_end_hook_timeout_ms,
    should_skip_hook_due_to_trust,
    create_base_hook_input,
    IfConditionMatcher,
    # Query / matching utilities
    get_matching_hooks,
    matches_pattern,
    prepare_if_condition_matcher,
    get_plugin_hook_counts,
    get_hook_type_counts,
    has_hook_for_event,
    # Error-message formatters
    get_pre_tool_hook_blocking_message,
    get_stop_hook_message,
    get_teammate_idle_hook_message,
    get_task_created_hook_message,
    get_task_completed_hook_message,
    get_user_prompt_submit_hook_blocking_message,
)

# ---------------------------------------------------------------------------
# Execution engine (from hooks_execute.py)
# ---------------------------------------------------------------------------
from claude_code.utils.hooks_execute import (
    # Additional type aliases defined in execute layer
    HookOutsideReplResult,
    ElicitationHookResult,
    ElicitationResultHookResult,
    ConfigChangeSource,
    InstructionsLoadReason,
    InstructionsMemoryType,

    # Utility
    has_blocking_result,
    has_instructions_loaded_hook,
    has_worktree_create_hook,

    # Async-generator hook executors (REPL context)
    execute_pre_tool_hooks,
    execute_post_tool_hooks,
    execute_post_tool_use_failure_hooks,
    execute_permission_denied_hooks,
    execute_permission_request_hooks,
    execute_stop_hooks,
    execute_stop_failure_hooks,
    execute_subagent_start_hooks,
    execute_session_start_hooks,
    execute_setup_hooks,
    execute_user_prompt_submit_hooks,
    execute_teammate_idle_hooks,
    execute_task_created_hooks,
    execute_task_completed_hooks,

    # Coroutine hook executors (outside-REPL context)
    execute_notification_hooks,
    execute_session_end_hooks,
    execute_pre_compact_hooks,
    execute_post_compact_hooks,
    execute_config_change_hooks,
    execute_cwd_changed_hooks,
    execute_file_changed_hooks,
    execute_instructions_loaded_hooks,
    execute_elicitation_hooks,
    execute_elicitation_result_hooks,
    execute_worktree_create_hook,
    execute_worktree_remove_hook,

    # StatusLine / FileSuggestion
    execute_status_line_command,
    execute_file_suggestion_command,
)

# ---------------------------------------------------------------------------
# __all__ — the complete public API (mirrors hooks.ts exports)
# ---------------------------------------------------------------------------
__all__ = [
    # ── Constants ──────────────────────────────────────────────────────────
    "TOOL_HOOK_EXECUTION_TIMEOUT_MS",
    "SESSION_END_HOOK_TIMEOUT_MS_DEFAULT",

    # ── Hook event names ───────────────────────────────────────────────────
    "HookEvent",
    "HookEventName",
    "ExtendedHookEvent",

    # ── Input types ────────────────────────────────────────────────────────
    "BaseHookInput",
    "HookInput",
    "PreToolUseHookInput",
    "PostToolUseHookInput",
    "PostToolUseFailureHookInput",
    "PermissionDeniedHookInput",
    "PermissionRequestHookInput",
    "NotificationHookInput",
    "SessionStartHookInput",
    "SessionEndHookInput",
    "SetupHookInput",
    "StopHookInput",
    "StopFailureHookInput",
    "SubagentStartHookInput",
    "SubagentStopHookInput",
    "TeammateIdleHookInput",
    "TaskCreatedHookInput",
    "TaskCompletedHookInput",
    "ConfigChangeHookInput",
    "CwdChangedHookInput",
    "FileChangedHookInput",
    "InstructionsLoadedHookInput",
    "UserPromptSubmitHookInput",
    "ElicitationHookInput",
    "ElicitationResultHookInput",
    "PreCompactHookInput",
    "PostCompactHookInput",

    # ── JSON output types ──────────────────────────────────────────────────
    "SyncHookJSONOutput",
    "AsyncHookJSONOutput",
    "HookJSONOutput",
    "HookSpecificOutput",

    # ── Hook definition types ──────────────────────────────────────────────
    "HookCommand",
    "HookCallback",
    "FunctionHook",
    "MatchedHook",

    # ── Result types ───────────────────────────────────────────────────────
    "HookResult",
    "AggregatedHookResult",
    "HookResultMessage",
    "HookBlockingError",
    "HookOutsideReplResult",
    "ElicitationResponse",
    "ElicitationHookResult",
    "ElicitationResultHookResult",

    # ── Permission types ───────────────────────────────────────────────────
    "PermissionBehavior",
    "PermissionUpdate",
    "PermissionRequestResult",
    "PermissionRequestResultAllow",
    "PermissionRequestResultDeny",

    # ── Misc types / aliases ───────────────────────────────────────────────
    "ExitReason",
    "ConfigChangeSource",
    "InstructionsLoadReason",
    "InstructionsMemoryType",
    "IfConditionMatcher",

    # ── Type predicates ────────────────────────────────────────────────────
    "is_async_hook_json_output",
    "is_sync_hook_json_output",

    # ── Core helpers ───────────────────────────────────────────────────────
    "get_session_end_hook_timeout_ms",
    "should_skip_hook_due_to_trust",
    "create_base_hook_input",

    # ── Query / utility functions ──────────────────────────────────────────
    "has_blocking_result",
    "has_hook_for_event",
    "has_instructions_loaded_hook",
    "has_worktree_create_hook",
    "get_matching_hooks",
    "get_plugin_hook_counts",
    "get_hook_type_counts",
    "matches_pattern",
    "prepare_if_condition_matcher",

    # ── Error message formatters ───────────────────────────────────────────
    "get_pre_tool_hook_blocking_message",
    "get_stop_hook_message",
    "get_teammate_idle_hook_message",
    "get_task_created_hook_message",
    "get_task_completed_hook_message",
    "get_user_prompt_submit_hook_blocking_message",

    # ── Async-generator hook executors (REPL) ─────────────────────────────
    "execute_pre_tool_hooks",
    "execute_post_tool_hooks",
    "execute_post_tool_use_failure_hooks",
    "execute_permission_denied_hooks",
    "execute_permission_request_hooks",
    "execute_stop_hooks",
    "execute_stop_failure_hooks",
    "execute_subagent_start_hooks",
    "execute_session_start_hooks",
    "execute_setup_hooks",
    "execute_user_prompt_submit_hooks",
    "execute_teammate_idle_hooks",
    "execute_task_created_hooks",
    "execute_task_completed_hooks",

    # ── Coroutine hook executors (outside-REPL) ───────────────────────────
    "execute_notification_hooks",
    "execute_session_end_hooks",
    "execute_pre_compact_hooks",
    "execute_post_compact_hooks",
    "execute_config_change_hooks",
    "execute_cwd_changed_hooks",
    "execute_file_changed_hooks",
    "execute_instructions_loaded_hooks",
    "execute_elicitation_hooks",
    "execute_elicitation_result_hooks",
    "execute_worktree_create_hook",
    "execute_worktree_remove_hook",

    # ── StatusLine / FileSuggestion ────────────────────────────────────────
    "execute_status_line_command",
    "execute_file_suggestion_command",
]
