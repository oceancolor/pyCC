"""
hooks_core.py - Core hook functions for Claude Code Hooks system.

Ported from: utils/hooks.ts (lines 180-1900 core logic)

Covers:
  - shouldSkipHookDueToTrust()
  - createBaseHookInput()
  - matchesPattern()
  - prepareIfConditionMatcher()
  - getMatchingHooks()
  - Blocking message helpers (getPreToolHookBlockingMessage, etc.)
  - getSessionEndHookTimeoutMs()
"""
from __future__ import annotations

import os
import re
import asyncio
import logging
from os.path import basename
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from .hooks_types import (
    TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    SESSION_END_HOOK_TIMEOUT_MS_DEFAULT,
    HookEvent,
    HookInput,
    HookResult,
    AggregatedHookResult,
    HookBlockingError,
    MatchedHook,
    HookCommand,
    HookCallback,
    FunctionHook,
    PreToolUseHookInput,
    PostToolUseHookInput,
    PostToolUseFailureHookInput,
    PermissionRequestHookInput,
    PermissionDeniedHookInput,
    SessionStartHookInput,
    SessionEndHookInput,
    SetupHookInput,
    SubagentStartHookInput,
    SubagentStopHookInput,
    StopHookInput,
    StopFailureHookInput,
    ElicitationHookInput,
    ElicitationResultHookInput,
    ConfigChangeHookInput,
    InstructionsLoadedHookInput,
    FileChangedHookInput,
    NotificationHookInput,
    PreCompactHookInput,
    PostCompactHookInput,
    is_async_hook_json_output,
    SyncHookJSONOutput,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timeout helper
# ---------------------------------------------------------------------------


def get_session_end_hook_timeout_ms() -> int:
    """
    Returns the timeout for SessionEnd hooks (milliseconds).

    Overridable via CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS env var
    for users whose teardown scripts need more time.
    """
    raw = os.environ.get("CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS")
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return SESSION_END_HOOK_TIMEOUT_MS_DEFAULT


# ---------------------------------------------------------------------------
# Trust check
# ---------------------------------------------------------------------------


def should_skip_hook_due_to_trust() -> bool:
    """
    Checks if a hook should be skipped due to lack of workspace trust.

    ALL hooks require workspace trust because they execute arbitrary commands
    from .claude/settings.json. This is a defense-in-depth security measure.

    In non-interactive mode (SDK), trust is implicit — always execute.
    In interactive mode, ALL hooks require trust.

    Returns True if hook should be skipped, False if it should execute.
    """
    # Lazy imports to avoid circular dependency at module level
    try:
        from ..bootstrap.state import get_is_non_interactive_session
        from .config import check_has_trust_dialog_accepted

        # In non-interactive mode (SDK), trust is implicit
        is_interactive = not get_is_non_interactive_session()
        if not is_interactive:
            return False

        # In interactive mode, ALL hooks require trust
        has_trust = check_has_trust_dialog_accepted()
        return not has_trust
    except ImportError:
        # Fallback: if we can't check trust, skip the hook to be safe
        logger.debug(
            "Could not check trust state — defaulting to skip hook (safe fallback)"
        )
        return True


# ---------------------------------------------------------------------------
# createBaseHookInput
# ---------------------------------------------------------------------------


def create_base_hook_input(
    permission_mode: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_info: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, Any]:
    """
    Creates the base hook input that's common to all hook types.

    Args:
        permission_mode: Optional permission mode string.
        session_id: Optional session ID; falls back to getSessionId().
        agent_info: Optional dict with 'agent_id' and/or 'agent_type'.

    Returns:
        Dict with session_id, transcript_path, cwd, permission_mode,
        agent_id, agent_type.
    """
    try:
        from ..bootstrap.state import (
            get_session_id,
            get_main_thread_agent_type,
        )
        from .session_storage import get_transcript_path_for_session
        from .cwd import get_cwd

        resolved_session_id = session_id or get_session_id()
        # agent_type: subagent's type (from agent_info) takes precedence
        # over the session's --agent flag.
        resolved_agent_type = (
            (agent_info or {}).get("agent_type") or get_main_thread_agent_type()
        )

        return {
            "session_id": resolved_session_id,
            "transcript_path": get_transcript_path_for_session(resolved_session_id),
            "cwd": get_cwd(),
            "permission_mode": permission_mode,
            "agent_id": (agent_info or {}).get("agent_id"),
            "agent_type": resolved_agent_type,
        }
    except ImportError:
        # Fallback for environments where bootstrap state is not available
        resolved_session_id = session_id or "unknown-session"
        return {
            "session_id": resolved_session_id,
            "transcript_path": "",
            "cwd": os.getcwd(),
            "permission_mode": permission_mode,
            "agent_id": (agent_info or {}).get("agent_id"),
            "agent_type": (agent_info or {}).get("agent_type"),
        }


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------


def matches_pattern(match_query: str, matcher: str) -> bool:
    """
    Check if a match query matches a hook matcher pattern.

    Args:
        match_query: The query to match (e.g., 'Write', 'Edit', 'Bash')
        matcher: The matcher pattern — can be:
            - Simple string for exact match (e.g., 'Write')
            - Pipe-separated list for multiple exact matches (e.g., 'Write|Edit')
            - Regex pattern (e.g., '^Write.*', '.*', '^(Write|Edit)$')

    Returns:
        True if the query matches the pattern.
    """
    if not matcher or matcher == "*":
        return True

    # Normalize legacy tool names for comparison
    try:
        from .permissions.permission_rule_parser import normalize_legacy_tool_name, get_legacy_tool_names
        normalized_query = normalize_legacy_tool_name(match_query)
    except ImportError:
        normalized_query = match_query
        get_legacy_tool_names = lambda name: []  # type: ignore[assignment]

    # Check if it's a simple string or pipe-separated list (no regex special chars except |)
    if re.match(r"^[a-zA-Z0-9_|]+$", matcher):
        if "|" in matcher:
            try:
                from .permissions.permission_rule_parser import normalize_legacy_tool_name as _nlt
                patterns = [_nlt(p.strip()) for p in matcher.split("|")]
            except ImportError:
                patterns = [p.strip() for p in matcher.split("|")]
            return normalized_query in patterns
        # Simple exact match
        try:
            from .permissions.permission_rule_parser import normalize_legacy_tool_name as _nlt
            return normalized_query == _nlt(matcher)
        except ImportError:
            return normalized_query == matcher

    # Otherwise treat as regex
    try:
        pattern = re.compile(matcher)
        if pattern.search(match_query):
            return True
        # Also test against legacy names so patterns like "^Task$" still match
        try:
            for legacy_name in get_legacy_tool_names(match_query):
                if pattern.search(legacy_name):
                    return True
        except Exception:
            pass
        return False
    except re.error:
        logger.debug(f"Invalid regex pattern in hook matcher: {matcher!r}")
        return False


# ---------------------------------------------------------------------------
# If-condition matcher
# ---------------------------------------------------------------------------

IfConditionMatcher = Callable[[str], bool]


async def prepare_if_condition_matcher(
    hook_input: HookInput,
    tools: Optional[Any] = None,
) -> Optional[IfConditionMatcher]:
    """
    Prepare a matcher for hook `if` conditions.

    Expensive work (tool lookup, schema validation) happens once here; the
    returned closure is called per hook. Returns None for non-tool events.

    Args:
        hook_input: The hook input to match against.
        tools: Optional tools registry.

    Returns:
        A callable that takes an if-condition string and returns bool,
        or None if this event type doesn't support if-conditions.
    """
    event_name = hook_input.get("hook_event_name")  # type: ignore[call-overload]
    if event_name not in (
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionRequest",
    ):
        return None

    tool_name_raw: str = hook_input.get("tool_name", "")  # type: ignore[call-overload]

    try:
        from .permissions.permission_rule_parser import (
            normalize_legacy_tool_name,
            permission_rule_value_from_string,
        )
        tool_name = normalize_legacy_tool_name(tool_name_raw)
    except ImportError:
        tool_name = tool_name_raw

        def _no_normalize(s: str) -> str:
            return s

        def permission_rule_value_from_string(s: str) -> Any:  # type: ignore[misc]
            # fallback: treat entire string as tool name
            class _R:
                tool_name = s
                rule_content = None
            return _R()

    # Try to find the tool and validate input for pattern matching
    pattern_matcher: Optional[Callable[[str], bool]] = None
    if tools is not None:
        try:
            from ..tool import find_tool_by_name
            tool = find_tool_by_name(tools, tool_name_raw)
            if tool is not None:
                tool_input = hook_input.get("tool_input", {})  # type: ignore[call-overload]
                if hasattr(tool, "input_schema"):
                    try:
                        schema = tool.input_schema()
                        # Basic validation: just use the raw input dict
                        validated_input = tool_input
                    except Exception:
                        validated_input = None
                else:
                    validated_input = None

                if (
                    validated_input is not None
                    and hasattr(tool, "prepare_permission_matcher")
                ):
                    pattern_matcher = await tool.prepare_permission_matcher(
                        validated_input
                    )
        except (ImportError, Exception) as exc:
            logger.debug(f"Could not prepare pattern matcher for tool: {exc}")

    def if_condition_matcher(if_condition: str) -> bool:
        try:
            parsed = permission_rule_value_from_string(if_condition)
        except Exception:
            return False

        try:
            from .permissions.permission_rule_parser import normalize_legacy_tool_name as _nlt
            parsed_tool_name = _nlt(parsed.tool_name)
        except (ImportError, AttributeError):
            parsed_tool_name = getattr(parsed, "tool_name", if_condition)

        if parsed_tool_name != tool_name:
            return False

        rule_content = getattr(parsed, "rule_content", None)
        if not rule_content:
            return True

        return pattern_matcher(rule_content) if pattern_matcher else False

    return if_condition_matcher


# ---------------------------------------------------------------------------
# Internal hook helpers
# ---------------------------------------------------------------------------


def _is_internal_hook(matched: MatchedHook) -> bool:
    """Returns True if the hook is an internal callback hook."""
    hook = matched.hook
    return (
        isinstance(hook, dict)
        and hook.get("type") == "callback"
        and hook.get("internal") is True
    )


def _hook_dedup_key(matched: MatchedHook, payload: str) -> str:
    """
    Build a dedup key for a matched hook, namespaced by source context.

    Settings-file hooks (no plugin_root/skill_root) share the '' prefix so the
    same command defined in user/project/local still collapses to one.
    Plugin/skill hooks get their root as the prefix, so two plugins sharing an
    unexpanded template don't collapse.
    """
    prefix = matched.plugin_root or matched.skill_root or ""
    return f"{prefix}\x00{payload}"


def _get_if_condition(hook: Any) -> str:
    """Extract the `if` field from a hook dict."""
    if isinstance(hook, dict):
        return hook.get("if", "") or hook.get("if_", "") or ""
    return ""


# ---------------------------------------------------------------------------
# getHooksConfig (internal)
# ---------------------------------------------------------------------------


def _get_hooks_config(
    app_state: Optional[Any],
    session_id: str,
    hook_event: HookEvent,
) -> List[Any]:
    """
    Assemble the merged list of hook matchers for a given event.

    Mirrors the TypeScript getHooksConfig() function.
    """
    hooks: List[Any] = []

    # 1. Snapshot-based hooks (from settings files)
    try:
        from .hooks.hooks_config_snapshot import (
            get_hooks_config_from_snapshot,
            should_allow_managed_hooks_only,
        )
        snapshot = get_hooks_config_from_snapshot()
        if snapshot:
            event_hooks = snapshot.get(hook_event, [])
            hooks.extend(event_hooks)
        managed_only = should_allow_managed_hooks_only()
    except ImportError:
        managed_only = False

    # 2. Registered hooks (SDK callbacks and plugin native hooks)
    try:
        from ..bootstrap.state import get_registered_hooks
        registered = get_registered_hooks()
        if registered:
            event_registered = registered.get(hook_event)
            if event_registered:
                for matcher in event_registered:
                    # Skip plugin hooks when restricted to managed hooks only
                    if managed_only and hasattr(matcher, "plugin_root"):
                        continue
                    hooks.append(matcher)
    except ImportError:
        pass

    # 3. Session hooks (scoped to current session)
    if not managed_only and app_state is not None:
        try:
            from .hooks.session_hooks import get_session_hooks, get_session_function_hooks
            session_hooks_map = get_session_hooks(app_state, session_id, hook_event)
            session_hooks = session_hooks_map.get(hook_event)
            if session_hooks:
                hooks.extend(session_hooks)

            func_hooks_map = get_session_function_hooks(app_state, session_id, hook_event)
            func_hooks = func_hooks_map.get(hook_event)
            if func_hooks:
                hooks.extend(func_hooks)
        except (ImportError, Exception) as exc:
            logger.debug(f"Could not load session hooks: {exc}")

    return hooks


# ---------------------------------------------------------------------------
# hasHookForEvent (lightweight existence check)
# ---------------------------------------------------------------------------


def has_hook_for_event(
    hook_event: HookEvent,
    app_state: Optional[Any],
    session_id: str,
) -> bool:
    """
    Lightweight existence check for hooks on a given event.

    Intentionally over-approximates: returns True if any matcher exists,
    even if filtering would later discard it.
    """
    try:
        from .hooks.hooks_config_snapshot import get_hooks_config_from_snapshot
        snap = get_hooks_config_from_snapshot()
        if snap and snap.get(hook_event):
            return True
    except ImportError:
        pass

    try:
        from ..bootstrap.state import get_registered_hooks
        reg = get_registered_hooks()
        if reg and reg.get(hook_event):
            return True
    except ImportError:
        pass

    if app_state is not None:
        try:
            session_hooks = getattr(app_state, "session_hooks", None)
            if session_hooks:
                session_data = session_hooks.get(session_id)
                if session_data:
                    hooks_dict = getattr(session_data, "hooks", {})
                    if hooks_dict.get(hook_event):
                        return True
        except Exception:
            pass

    return False


# ---------------------------------------------------------------------------
# getMatchingHooks
# ---------------------------------------------------------------------------


async def get_matching_hooks(
    app_state: Optional[Any],
    session_id: str,
    hook_event: HookEvent,
    hook_input: HookInput,
    tools: Optional[Any] = None,
) -> List[MatchedHook]:
    """
    Get hook commands that match the given query.

    Args:
        app_state: The current app state (optional for backwards compatibility).
        session_id: The current session ID (main session or agent ID).
        hook_event: The hook event.
        hook_input: The hook input for matching.
        tools: Optional tools registry for `if` condition matching.

    Returns:
        List of matched hooks with optional plugin context.
    """
    try:
        hook_matchers = _get_hooks_config(app_state, session_id, hook_event)

        # Determine the match query based on event type
        match_query: Optional[str] = None
        event_name = hook_input.get("hook_event_name")  # type: ignore[call-overload]

        if event_name in (
            "PreToolUse",
            "PostToolUse",
            "PostToolUseFailure",
            "PermissionRequest",
            "PermissionDenied",
        ):
            match_query = hook_input.get("tool_name")  # type: ignore[call-overload]
        elif event_name == "SessionStart":
            match_query = hook_input.get("source")  # type: ignore[call-overload]
        elif event_name == "Setup":
            match_query = hook_input.get("trigger")  # type: ignore[call-overload]
        elif event_name in ("PreCompact", "PostCompact"):
            match_query = hook_input.get("trigger")  # type: ignore[call-overload]
        elif event_name == "Notification":
            match_query = hook_input.get("notification_type")  # type: ignore[call-overload]
        elif event_name == "SessionEnd":
            match_query = hook_input.get("reason")  # type: ignore[call-overload]
        elif event_name == "StopFailure":
            match_query = hook_input.get("error")  # type: ignore[call-overload]
        elif event_name in ("SubagentStart", "SubagentStop"):
            match_query = hook_input.get("agent_type")  # type: ignore[call-overload]
        elif event_name in ("TeammateIdle", "TaskCreated", "TaskCompleted"):
            match_query = None
        elif event_name in ("Elicitation", "ElicitationResult"):
            match_query = hook_input.get("mcp_server_name")  # type: ignore[call-overload]
        elif event_name == "ConfigChange":
            match_query = hook_input.get("source")  # type: ignore[call-overload]
        elif event_name == "InstructionsLoaded":
            match_query = hook_input.get("load_reason")  # type: ignore[call-overload]
        elif event_name == "FileChanged":
            file_path = hook_input.get("file_path", "")  # type: ignore[call-overload]
            match_query = basename(file_path) if file_path else None

        logger.debug(
            f"Getting matching hook commands for {hook_event} with query: {match_query}"
        )
        logger.debug(f"Found {len(hook_matchers)} hook matchers in settings")

        # Filter matchers by matcher pattern
        if match_query is not None:
            filtered_matchers = [
                m
                for m in hook_matchers
                if not _get_matcher_field(m) or matches_pattern(match_query, _get_matcher_field(m))
            ]
        else:
            filtered_matchers = hook_matchers

        # Extract hooks with their plugin context
        matched_hooks: List[MatchedHook] = []
        for matcher in filtered_matchers:
            plugin_root = _get_field(matcher, "plugin_root") or _get_field(matcher, "pluginRoot")
            plugin_id = _get_field(matcher, "plugin_id") or _get_field(matcher, "pluginId")
            skill_root = _get_field(matcher, "skill_root") or _get_field(matcher, "skillRoot")

            # Determine hook source label
            if plugin_root:
                plugin_name = _get_field(matcher, "plugin_name") or _get_field(matcher, "pluginName")
                hook_source = f"plugin:{plugin_name}" if plugin_name else "plugin"
            elif skill_root:
                skill_name = _get_field(matcher, "skill_name") or _get_field(matcher, "skillName")
                hook_source = f"skill:{skill_name}" if skill_name else "skill"
            else:
                hook_source = "settings"

            hooks_list = _get_field(matcher, "hooks") or []
            if not isinstance(hooks_list, (list, tuple)):
                hooks_list = [hooks_list]

            for hook in hooks_list:
                matched_hooks.append(
                    MatchedHook(
                        hook=hook,
                        plugin_root=plugin_root,
                        plugin_id=plugin_id,
                        skill_root=skill_root,
                        hook_source=hook_source,
                    )
                )

        # Fast-path: callback/function hooks don't need dedup
        if all(
            _get_hook_type(m.hook) in ("callback", "function")
            for m in matched_hooks
        ):
            return matched_hooks

        # Deduplicate hooks by command/prompt/url within the same source context
        def _dedup(
            hooks_seq: List[MatchedHook],
            key_fn: Callable[[MatchedHook], str],
        ) -> List[MatchedHook]:
            seen: Dict[str, MatchedHook] = {}
            for h in hooks_seq:
                k = key_fn(h)
                seen[k] = h  # last one wins (matches TS Map behavior)
            return list(seen.values())

        default_shell = _get_default_hook_shell()

        unique_command_hooks = _dedup(
            [m for m in matched_hooks if _get_hook_type(m.hook) == "command"],
            lambda m: _hook_dedup_key(
                m,
                f"{_get_field(m.hook, 'shell') or default_shell}\x00"
                f"{_get_field(m.hook, 'command') or ''}\x00"
                f"{_get_if_condition(m.hook)}",
            ),
        )
        unique_prompt_hooks = _dedup(
            [m for m in matched_hooks if _get_hook_type(m.hook) == "prompt"],
            lambda m: _hook_dedup_key(
                m,
                f"{_get_field(m.hook, 'prompt') or ''}\x00{_get_if_condition(m.hook)}",
            ),
        )
        unique_agent_hooks = _dedup(
            [m for m in matched_hooks if _get_hook_type(m.hook) == "agent"],
            lambda m: _hook_dedup_key(
                m,
                f"{_get_field(m.hook, 'prompt') or ''}\x00{_get_if_condition(m.hook)}",
            ),
        )
        unique_http_hooks = _dedup(
            [m for m in matched_hooks if _get_hook_type(m.hook) == "http"],
            lambda m: _hook_dedup_key(
                m,
                f"{_get_field(m.hook, 'url') or ''}\x00{_get_if_condition(m.hook)}",
            ),
        )
        callback_hooks = [m for m in matched_hooks if _get_hook_type(m.hook) == "callback"]
        function_hooks = [m for m in matched_hooks if _get_hook_type(m.hook) == "function"]

        unique_hooks = (
            unique_command_hooks
            + unique_prompt_hooks
            + unique_agent_hooks
            + unique_http_hooks
            + callback_hooks
            + function_hooks
        )

        # Filter hooks based on their `if` condition
        has_if_condition = any(
            _get_hook_type(h.hook) in ("command", "prompt", "agent", "http")
            and _get_if_condition(h.hook)
            for h in unique_hooks
        )
        if_matcher = (
            await prepare_if_condition_matcher(hook_input, tools)
            if has_if_condition
            else None
        )

        def _passes_if_filter(m: MatchedHook) -> bool:
            hook_type = _get_hook_type(m.hook)
            if hook_type not in ("command", "prompt", "agent", "http"):
                return True
            if_condition = _get_if_condition(m.hook)
            if not if_condition:
                return True
            if if_matcher is None:
                logger.debug(
                    f"Hook if condition {if_condition!r} cannot be evaluated "
                    f"for non-tool event {event_name}"
                )
                return False
            if if_matcher(if_condition):
                return True
            logger.debug(
                f"Skipping hook due to if condition {if_condition!r} not matching"
            )
            return False

        if_filtered_hooks = [h for h in unique_hooks if _passes_if_filter(h)]

        # HTTP hooks are not supported for SessionStart/Setup events
        if hook_event in ("SessionStart", "Setup"):
            filtered_hooks = []
            for h in if_filtered_hooks:
                if _get_hook_type(h.hook) == "http":
                    url = _get_field(h.hook, "url") or ""
                    logger.debug(
                        f"Skipping HTTP hook {url!r} — HTTP hooks are not "
                        f"supported for {hook_event}"
                    )
                else:
                    filtered_hooks.append(h)
        else:
            filtered_hooks = if_filtered_hooks

        logger.debug(
            f"Matched {len(filtered_hooks)} unique hooks for query "
            f"{match_query!r} ({len(matched_hooks)} before deduplication)"
        )
        return filtered_hooks

    except Exception as exc:
        logger.debug(f"get_matching_hooks failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Blocking message helpers
# ---------------------------------------------------------------------------


def get_pre_tool_hook_blocking_message(
    hook_name: str,
    blocking_error: HookBlockingError,
) -> str:
    """
    Format a blocking error from a PreTool hook.

    Args:
        hook_name: The name of the hook (e.g., 'PreToolUse:Write').
        blocking_error: The blocking error from the hook.

    Returns:
        Formatted blocking message string.
    """
    return f"{hook_name} hook error: {blocking_error.blocking_error}"


def get_stop_hook_message(blocking_error: HookBlockingError) -> str:
    """
    Format a blocking error from a Stop hook.

    Args:
        blocking_error: The blocking error from the hook.

    Returns:
        Formatted message to give feedback to the model.
    """
    return f"Stop hook feedback:\n{blocking_error.blocking_error}"


def get_teammate_idle_hook_message(blocking_error: HookBlockingError) -> str:
    """
    Format a blocking error from a TeammateIdle hook.

    Args:
        blocking_error: The blocking error from the hook.

    Returns:
        Formatted message to give feedback to the model.
    """
    return f"TeammateIdle hook feedback:\n{blocking_error.blocking_error}"


def get_task_created_hook_message(blocking_error: HookBlockingError) -> str:
    """
    Format a blocking error from a TaskCreated hook.

    Args:
        blocking_error: The blocking error from the hook.

    Returns:
        Formatted message to give feedback to the model.
    """
    return f"TaskCreated hook feedback:\n{blocking_error.blocking_error}"


def get_task_completed_hook_message(blocking_error: HookBlockingError) -> str:
    """
    Format a blocking error from a TaskCompleted hook.

    Args:
        blocking_error: The blocking error from the hook.

    Returns:
        Formatted message to give feedback to the model.
    """
    return f"TaskCompleted hook feedback:\n{blocking_error.blocking_error}"


def get_user_prompt_submit_hook_blocking_message(
    blocking_error: HookBlockingError,
) -> str:
    """
    Format a blocking error from a UserPromptSubmit hook.

    Args:
        blocking_error: The blocking error from the hook.

    Returns:
        Formatted blocking message string.
    """
    return (
        f"UserPromptSubmit operation blocked by hook:\n{blocking_error.blocking_error}"
    )


# ---------------------------------------------------------------------------
# Private utility helpers
# ---------------------------------------------------------------------------


def _get_field(obj: Any, key: str) -> Any:
    """Get a field from a dict or object attribute."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _get_matcher_field(obj: Any) -> str:
    """Get the 'matcher' field from a hook matcher object."""
    v = _get_field(obj, "matcher")
    return v if isinstance(v, str) else ""


def _get_hook_type(hook: Any) -> str:
    """Get the type of a hook (command/callback/function/prompt/agent/http)."""
    if isinstance(hook, dict):
        return hook.get("type", "")
    return getattr(hook, "type", "")


def _get_default_hook_shell() -> str:
    """Get the default hook shell setting."""
    try:
        from .shell.shell_provider import DEFAULT_HOOK_SHELL
        return DEFAULT_HOOK_SHELL
    except ImportError:
        return "bash"


# ---------------------------------------------------------------------------
# Plugin hook counts helpers (analytics)
# ---------------------------------------------------------------------------

# Allowed official marketplace names (subset — full list in plugins/schemas.py)
_ALLOWED_OFFICIAL_MARKETPLACE_NAMES: frozenset[str] = frozenset()


def get_plugin_hook_counts(hooks: List[MatchedHook]) -> Optional[Dict[str, int]]:
    """
    Build a map of {sanitizedPluginName: hookCount} from matched hooks.
    Only logs actual names for official marketplace plugins; others become 'third-party'.
    """
    plugin_hooks = [h for h in hooks if h.plugin_id]
    if not plugin_hooks:
        return None

    try:
        from .plugins.schemas import ALLOWED_OFFICIAL_MARKETPLACE_NAMES as _names
        allowed_names: frozenset[str] = _names
    except ImportError:
        allowed_names = _ALLOWED_OFFICIAL_MARKETPLACE_NAMES

    counts: Dict[str, int] = {}
    for h in plugin_hooks:
        plugin_id = h.plugin_id or ""
        at_index = plugin_id.rfind("@")
        is_official = (
            at_index > 0 and plugin_id[at_index + 1:] in allowed_names
        )
        key = plugin_id if is_official else "third-party"
        counts[key] = counts.get(key, 0) + 1
    return counts


def get_hook_type_counts(hooks: List[MatchedHook]) -> Dict[str, int]:
    """Build a map of {hookType: count} from matched hooks."""
    counts: Dict[str, int] = {}
    for h in hooks:
        t = _get_hook_type(h.hook)
        counts[t] = counts.get(t, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    # Timeout
    "get_session_end_hook_timeout_ms",
    # Trust check
    "should_skip_hook_due_to_trust",
    # Base input
    "create_base_hook_input",
    # Pattern matching
    "matches_pattern",
    # If-condition
    "prepare_if_condition_matcher",
    "IfConditionMatcher",
    # Hooks config
    "has_hook_for_event",
    "get_matching_hooks",
    # Blocking message helpers
    "get_pre_tool_hook_blocking_message",
    "get_stop_hook_message",
    "get_teammate_idle_hook_message",
    "get_task_created_hook_message",
    "get_task_completed_hook_message",
    "get_user_prompt_submit_hook_blocking_message",
    # Analytics helpers
    "get_plugin_hook_counts",
    "get_hook_type_counts",
]
