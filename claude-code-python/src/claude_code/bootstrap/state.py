"""bootstrap/state.py — Global session state singleton.

Python port of bootstrap/state.ts.
Single module-level _STATE dict + accessor functions.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# ChannelEntry
# {'kind': 'plugin', 'name': str, 'marketplace': str, 'dev': bool | None}
# {'kind': 'server', 'name': str, 'dev': bool | None}
ChannelEntry = dict

# SessionCronTask
# {id, cron, prompt, created_at, recurring?, agent_id?}
SessionCronTask = dict

# InvokedSkillInfo
InvokedSkillInfo = dict  # {skill_name, skill_path, content, invoked_at, agent_id}

# ---------------------------------------------------------------------------
# Signal (minimal pub/sub replacement for createSignal)
# ---------------------------------------------------------------------------

class _Signal:
    def __init__(self):
        self._listeners: list[Callable] = []

    def emit(self, *args):
        for fn in list(self._listeners):
            fn(*args)

    def subscribe(self, fn: Callable) -> Callable:
        self._listeners.append(fn)
        def unsubscribe():
            self._listeners.remove(fn)
        return unsubscribe

    def clear(self):
        self._listeners.clear()


_session_switched = _Signal()

# ---------------------------------------------------------------------------
# Initial state factory
# ---------------------------------------------------------------------------

def _get_initial_state() -> dict:
    resolved_cwd = ""
    try:
        import os.path
        raw = os.getcwd()
        resolved_cwd = os.path.realpath(raw)
    except Exception:
        resolved_cwd = os.getcwd()

    return {
        "original_cwd": resolved_cwd,
        "project_root": resolved_cwd,
        "total_cost_usd": 0.0,
        "total_api_duration": 0,
        "total_api_duration_without_retries": 0,
        "total_tool_duration": 0,
        "turn_hook_duration_ms": 0,
        "turn_tool_duration_ms": 0,
        "turn_classifier_duration_ms": 0,
        "turn_tool_count": 0,
        "turn_hook_count": 0,
        "turn_classifier_count": 0,
        "start_time": _now_ms(),
        "last_interaction_time": _now_ms(),
        "total_lines_added": 0,
        "total_lines_removed": 0,
        "has_unknown_model_cost": False,
        "cwd": resolved_cwd,
        "model_usage": {},
        "main_loop_model_override": None,
        "initial_main_loop_model": None,
        "model_strings": None,
        "is_interactive": False,
        "kairos_active": False,
        "strict_tool_result_pairing": False,
        "sdk_agent_progress_summaries_enabled": False,
        "user_msg_opt_in": False,
        "client_type": "cli",
        "session_source": None,
        "question_preview_format": None,
        "flag_settings_path": None,
        "flag_settings_inline": None,
        "allowed_setting_sources": [
            "userSettings",
            "projectSettings",
            "localSettings",
            "flagSettings",
            "policySettings",
        ],
        "session_ingress_token": None,
        "oauth_token_from_fd": None,
        "api_key_from_fd": None,
        # Telemetry
        "meter": None,
        "session_counter": None,
        "loc_counter": None,
        "pr_counter": None,
        "commit_counter": None,
        "cost_counter": None,
        "token_counter": None,
        "code_edit_tool_decision_counter": None,
        "active_time_counter": None,
        "stats_store": None,
        "session_id": str(uuid.uuid4()),
        "parent_session_id": None,
        # Logger
        "logger_provider": None,
        "event_logger": None,
        # Meter/Tracer
        "meter_provider": None,
        "tracer_provider": None,
        # Agent color
        "agent_color_map": {},
        "agent_color_index": 0,
        # Last API request
        "last_api_request": None,
        "last_api_request_messages": None,
        "last_classifier_requests": None,
        "cached_claude_md_content": None,
        # In-memory error log
        "in_memory_error_log": [],
        # Plugins
        "inline_plugins": [],
        "chrome_flag_override": None,
        "use_cowork_plugins": False,
        # Session-only flags
        "session_bypass_permissions_mode": False,
        "scheduled_tasks_enabled": False,
        "session_cron_tasks": [],
        "session_created_teams": set(),
        "session_trust_accepted": False,
        "session_persistence_disabled": False,
        # Plan/auto mode
        "has_exited_plan_mode": False,
        "needs_plan_mode_exit_attachment": False,
        "needs_auto_mode_exit_attachment": False,
        # LSP
        "lsp_recommendation_shown_this_session": False,
        # SDK init
        "init_json_schema": None,
        "registered_hooks": None,
        # Plan slugs cache {session_id -> word_slug}
        "plan_slug_cache": {},
        # Teleport
        "teleported_session_info": None,
        # Invoked skills: key = "{agent_id}:{skill_name}"
        "invoked_skills": {},
        # Slow operations
        "slow_operations": [],
        # SDK betas
        "sdk_betas": None,
        # Main thread agent type
        "main_thread_agent_type": None,
        # Remote mode
        "is_remote_mode": False,
        # Direct connect server
        "direct_connect_server_url": None,
        # System prompt section cache
        "system_prompt_section_cache": {},
        # Last emitted date
        "last_emitted_date": None,
        # Additional dirs for CLAUDE.md
        "additional_directories_for_claude_md": [],
        # Allowed channels
        "allowed_channels": [],
        "has_dev_channels": False,
        # Session project dir
        "session_project_dir": None,
        # Prompt cache 1h
        "prompt_cache_1h_allowlist": None,
        "prompt_cache_1h_eligible": None,
        # Beta header latches
        "afk_mode_header_latched": None,
        "fast_mode_header_latched": None,
        "cache_editing_header_latched": None,
        "thinking_clear_latched": None,
        # Prompt / request tracking
        "prompt_id": None,
        "last_main_request_id": None,
        "last_api_completion_timestamp": None,
        "pending_post_compaction": False,
    }


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_STATE: dict = _get_initial_state()

# Module-level scroll drain state (ephemeral, not in _STATE)
_scroll_draining = False
_SCROLL_DRAIN_IDLE_MS = 150

# Token budget tracking (module-level like TS)
_output_tokens_at_turn_start = 0
_current_turn_token_budget: Optional[int] = None
_budget_continuation_count = 0

# Interaction time dirty flag
_interaction_time_dirty = False

# ---------------------------------------------------------------------------
# Session ID
# ---------------------------------------------------------------------------

def get_session_id() -> str:
    return _STATE["session_id"]


def regenerate_session_id(set_current_as_parent: bool = False) -> str:
    if set_current_as_parent:
        _STATE["parent_session_id"] = _STATE["session_id"]
    _STATE["plan_slug_cache"].pop(_STATE["session_id"], None)
    _STATE["session_id"] = str(uuid.uuid4())
    _STATE["session_project_dir"] = None
    return _STATE["session_id"]


def get_parent_session_id() -> Optional[str]:
    return _STATE["parent_session_id"]


def switch_session(session_id: str, project_dir: Optional[str] = None) -> None:
    _STATE["plan_slug_cache"].pop(_STATE["session_id"], None)
    _STATE["session_id"] = session_id
    _STATE["session_project_dir"] = project_dir
    _session_switched.emit(session_id)


on_session_switch = _session_switched.subscribe


def get_session_project_dir() -> Optional[str]:
    return _STATE["session_project_dir"]


# ---------------------------------------------------------------------------
# CWD / project root
# ---------------------------------------------------------------------------

def get_original_cwd() -> str:
    return _STATE["original_cwd"]


def get_project_root() -> str:
    return _STATE["project_root"]


def set_original_cwd(cwd: str) -> None:
    _STATE["original_cwd"] = cwd


def set_project_root(cwd: str) -> None:
    """Only for --worktree startup flag."""
    _STATE["project_root"] = cwd


def get_cwd_state() -> str:
    return _STATE["cwd"]


def set_cwd_state(cwd: str) -> None:
    _STATE["cwd"] = cwd


def get_direct_connect_server_url() -> Optional[str]:
    return _STATE["direct_connect_server_url"]


def set_direct_connect_server_url(url: str) -> None:
    _STATE["direct_connect_server_url"] = url


# ---------------------------------------------------------------------------
# Duration / cost
# ---------------------------------------------------------------------------

def add_to_total_duration_state(duration: int, duration_without_retries: int) -> None:
    _STATE["total_api_duration"] += duration
    _STATE["total_api_duration_without_retries"] += duration_without_retries


def reset_total_duration_state_and_cost_for_tests_only() -> None:
    _STATE["total_api_duration"] = 0
    _STATE["total_api_duration_without_retries"] = 0
    _STATE["total_cost_usd"] = 0.0


def add_to_total_cost_state(cost: float, model_usage: dict, model: str) -> None:
    _STATE["model_usage"][model] = model_usage
    _STATE["total_cost_usd"] += cost


def get_total_cost_usd() -> float:
    return _STATE["total_cost_usd"]


def get_total_api_duration() -> int:
    return _STATE["total_api_duration"]


def get_total_duration() -> int:
    return _now_ms() - _STATE["start_time"]


def get_total_api_duration_without_retries() -> int:
    return _STATE["total_api_duration_without_retries"]


def get_total_tool_duration() -> int:
    return _STATE["total_tool_duration"]


def add_to_tool_duration(duration: int) -> None:
    _STATE["total_tool_duration"] += duration
    _STATE["turn_tool_duration_ms"] += duration
    _STATE["turn_tool_count"] += 1


def get_turn_hook_duration_ms() -> int:
    return _STATE["turn_hook_duration_ms"]


def add_to_turn_hook_duration(duration: int) -> None:
    _STATE["turn_hook_duration_ms"] += duration
    _STATE["turn_hook_count"] += 1


def reset_turn_hook_duration() -> None:
    _STATE["turn_hook_duration_ms"] = 0
    _STATE["turn_hook_count"] = 0


def get_turn_hook_count() -> int:
    return _STATE["turn_hook_count"]


def get_turn_tool_duration_ms() -> int:
    return _STATE["turn_tool_duration_ms"]


def reset_turn_tool_duration() -> None:
    _STATE["turn_tool_duration_ms"] = 0
    _STATE["turn_tool_count"] = 0


def get_turn_tool_count() -> int:
    return _STATE["turn_tool_count"]


def get_turn_classifier_duration_ms() -> int:
    return _STATE["turn_classifier_duration_ms"]


def add_to_turn_classifier_duration(duration: int) -> None:
    _STATE["turn_classifier_duration_ms"] += duration
    _STATE["turn_classifier_count"] += 1


def reset_turn_classifier_duration() -> None:
    _STATE["turn_classifier_duration_ms"] = 0
    _STATE["turn_classifier_count"] = 0


def get_turn_classifier_count() -> int:
    return _STATE["turn_classifier_count"]


def get_stats_store() -> Optional[Any]:
    return _STATE["stats_store"]


def set_stats_store(store: Optional[Any]) -> None:
    _STATE["stats_store"] = store


# ---------------------------------------------------------------------------
# Interaction time
# ---------------------------------------------------------------------------

def update_last_interaction_time(immediate: bool = False) -> None:
    global _interaction_time_dirty
    if immediate:
        _flush_interaction_time_inner()
    else:
        _interaction_time_dirty = True


def flush_interaction_time() -> None:
    global _interaction_time_dirty
    if _interaction_time_dirty:
        _flush_interaction_time_inner()


def _flush_interaction_time_inner() -> None:
    global _interaction_time_dirty
    _STATE["last_interaction_time"] = _now_ms()
    _interaction_time_dirty = False


def get_last_interaction_time() -> int:
    return _STATE["last_interaction_time"]


# ---------------------------------------------------------------------------
# Lines changed
# ---------------------------------------------------------------------------

def add_to_total_lines_changed(added: int, removed: int) -> None:
    _STATE["total_lines_added"] += added
    _STATE["total_lines_removed"] += removed


def get_total_lines_added() -> int:
    return _STATE["total_lines_added"]


def get_total_lines_removed() -> int:
    return _STATE["total_lines_removed"]


# ---------------------------------------------------------------------------
# Token accounting
# ---------------------------------------------------------------------------

def get_total_input_tokens() -> int:
    return sum(v.get("inputTokens", 0) for v in _STATE["model_usage"].values())


def get_total_output_tokens() -> int:
    return sum(v.get("outputTokens", 0) for v in _STATE["model_usage"].values())


def get_total_cache_read_input_tokens() -> int:
    return sum(v.get("cacheReadInputTokens", 0) for v in _STATE["model_usage"].values())


def get_total_cache_creation_input_tokens() -> int:
    return sum(v.get("cacheCreationInputTokens", 0) for v in _STATE["model_usage"].values())


def get_total_web_search_requests() -> int:
    return sum(v.get("webSearchRequests", 0) for v in _STATE["model_usage"].values())


def get_turn_output_tokens() -> int:
    return get_total_output_tokens() - _output_tokens_at_turn_start


def get_current_turn_token_budget() -> Optional[int]:
    return _current_turn_token_budget


def snapshot_output_tokens_for_turn(budget: Optional[int]) -> None:
    global _output_tokens_at_turn_start, _current_turn_token_budget, _budget_continuation_count
    _output_tokens_at_turn_start = get_total_output_tokens()
    _current_turn_token_budget = budget
    _budget_continuation_count = 0


def get_budget_continuation_count() -> int:
    return _budget_continuation_count


def increment_budget_continuation_count() -> None:
    global _budget_continuation_count
    _budget_continuation_count += 1


def set_has_unknown_model_cost() -> None:
    _STATE["has_unknown_model_cost"] = True


def has_unknown_model_cost() -> bool:
    return _STATE["has_unknown_model_cost"]


def get_last_main_request_id() -> Optional[str]:
    return _STATE["last_main_request_id"]


def set_last_main_request_id(request_id: str) -> None:
    _STATE["last_main_request_id"] = request_id


def get_last_api_completion_timestamp() -> Optional[int]:
    return _STATE["last_api_completion_timestamp"]


def set_last_api_completion_timestamp(timestamp: int) -> None:
    _STATE["last_api_completion_timestamp"] = timestamp


def mark_post_compaction() -> None:
    _STATE["pending_post_compaction"] = True


def consume_post_compaction() -> bool:
    was = _STATE["pending_post_compaction"]
    _STATE["pending_post_compaction"] = False
    return was


# ---------------------------------------------------------------------------
# Scroll drain
# ---------------------------------------------------------------------------

def mark_scroll_activity() -> None:
    global _scroll_draining
    _scroll_draining = True
    # In Python we don't have setTimeout; callers should use asyncio or threading.
    # We provide a simple flag-based implementation.
    # Real async version would schedule clear after SCROLL_DRAIN_IDLE_MS.
    import threading
    def _clear():
        global _scroll_draining
        _scroll_draining = False
    t = threading.Timer(_SCROLL_DRAIN_IDLE_MS / 1000.0, _clear)
    t.daemon = True
    t.start()


def get_is_scroll_draining() -> bool:
    return _scroll_draining


async def wait_for_scroll_idle() -> None:
    import asyncio
    while _scroll_draining:
        await asyncio.sleep(_SCROLL_DRAIN_IDLE_MS / 1000.0)


# ---------------------------------------------------------------------------
# Model usage / model settings
# ---------------------------------------------------------------------------

def get_model_usage() -> dict:
    return _STATE["model_usage"]


def get_usage_for_model(model: str) -> Optional[dict]:
    return _STATE["model_usage"].get(model)


def get_main_loop_model_override() -> Optional[Any]:
    return _STATE["main_loop_model_override"]


def get_initial_main_loop_model() -> Any:
    return _STATE["initial_main_loop_model"]


def set_main_loop_model_override(model: Optional[Any]) -> None:
    _STATE["main_loop_model_override"] = model


def set_initial_main_loop_model(model: Any) -> None:
    _STATE["initial_main_loop_model"] = model


def get_sdk_betas() -> Optional[list]:
    return _STATE["sdk_betas"]


def set_sdk_betas(betas: Optional[list]) -> None:
    _STATE["sdk_betas"] = betas


def reset_cost_state() -> None:
    _STATE["total_cost_usd"] = 0.0
    _STATE["total_api_duration"] = 0
    _STATE["total_api_duration_without_retries"] = 0
    _STATE["total_tool_duration"] = 0
    _STATE["start_time"] = _now_ms()
    _STATE["total_lines_added"] = 0
    _STATE["total_lines_removed"] = 0
    _STATE["has_unknown_model_cost"] = False
    _STATE["model_usage"] = {}
    _STATE["prompt_id"] = None


def set_cost_state_for_restore(
    total_cost_usd: float,
    total_api_duration: int,
    total_api_duration_without_retries: int,
    total_tool_duration: int,
    total_lines_added: int,
    total_lines_removed: int,
    last_duration: Optional[int],
    model_usage: Optional[dict],
) -> None:
    _STATE["total_cost_usd"] = total_cost_usd
    _STATE["total_api_duration"] = total_api_duration
    _STATE["total_api_duration_without_retries"] = total_api_duration_without_retries
    _STATE["total_tool_duration"] = total_tool_duration
    _STATE["total_lines_added"] = total_lines_added
    _STATE["total_lines_removed"] = total_lines_removed
    if model_usage:
        _STATE["model_usage"] = model_usage
    if last_duration:
        _STATE["start_time"] = _now_ms() - last_duration


def reset_state_for_tests() -> None:
    """Only for tests."""
    if os.environ.get("NODE_ENV") != "test" and os.environ.get("PYTEST_CURRENT_TEST") is None:
        raise RuntimeError("reset_state_for_tests can only be called in tests")
    global _output_tokens_at_turn_start, _current_turn_token_budget, _budget_continuation_count
    _STATE.clear()
    _STATE.update(_get_initial_state())
    _output_tokens_at_turn_start = 0
    _current_turn_token_budget = None
    _budget_continuation_count = 0
    _session_switched.clear()


# ---------------------------------------------------------------------------
# Model strings
# ---------------------------------------------------------------------------

def get_model_strings() -> Optional[Any]:
    return _STATE["model_strings"]


def set_model_strings(model_strings: Any) -> None:
    _STATE["model_strings"] = model_strings


def reset_model_strings_for_testing_only() -> None:
    _STATE["model_strings"] = None


# ---------------------------------------------------------------------------
# Telemetry / meters
# ---------------------------------------------------------------------------

def set_meter(meter: Any, create_counter: Callable) -> None:
    _STATE["meter"] = meter
    _STATE["session_counter"] = create_counter("claude_code.session.count", {
        "description": "Count of CLI sessions started"
    })
    _STATE["loc_counter"] = create_counter("claude_code.lines_of_code.count", {
        "description": "Count of lines of code modified"
    })
    _STATE["pr_counter"] = create_counter("claude_code.pull_request.count", {
        "description": "Number of pull requests created"
    })
    _STATE["commit_counter"] = create_counter("claude_code.commit.count", {
        "description": "Number of git commits created"
    })
    _STATE["cost_counter"] = create_counter("claude_code.cost.usage", {
        "description": "Cost of the Claude Code session",
        "unit": "USD"
    })
    _STATE["token_counter"] = create_counter("claude_code.token.usage", {
        "description": "Number of tokens used",
        "unit": "tokens"
    })
    _STATE["code_edit_tool_decision_counter"] = create_counter(
        "claude_code.code_edit_tool.decision", {
            "description": "Count of code editing tool permission decisions"
        }
    )
    _STATE["active_time_counter"] = create_counter("claude_code.active_time.total", {
        "description": "Total active time in seconds",
        "unit": "s"
    })


def get_meter() -> Optional[Any]:
    return _STATE["meter"]


def get_session_counter() -> Optional[Any]:
    return _STATE["session_counter"]


def get_loc_counter() -> Optional[Any]:
    return _STATE["loc_counter"]


def get_pr_counter() -> Optional[Any]:
    return _STATE["pr_counter"]


def get_commit_counter() -> Optional[Any]:
    return _STATE["commit_counter"]


def get_cost_counter() -> Optional[Any]:
    return _STATE["cost_counter"]


def get_token_counter() -> Optional[Any]:
    return _STATE["token_counter"]


def get_code_edit_tool_decision_counter() -> Optional[Any]:
    return _STATE["code_edit_tool_decision_counter"]


def get_active_time_counter() -> Optional[Any]:
    return _STATE["active_time_counter"]


def get_logger_provider() -> Optional[Any]:
    return _STATE["logger_provider"]


def set_logger_provider(provider: Optional[Any]) -> None:
    _STATE["logger_provider"] = provider


def get_event_logger() -> Optional[Any]:
    return _STATE["event_logger"]


def set_event_logger(logger: Optional[Any]) -> None:
    _STATE["event_logger"] = logger


def get_meter_provider() -> Optional[Any]:
    return _STATE["meter_provider"]


def set_meter_provider(provider: Optional[Any]) -> None:
    _STATE["meter_provider"] = provider


def get_tracer_provider() -> Optional[Any]:
    return _STATE["tracer_provider"]


def set_tracer_provider(provider: Optional[Any]) -> None:
    _STATE["tracer_provider"] = provider


# ---------------------------------------------------------------------------
# Interactive / client type
# ---------------------------------------------------------------------------

def get_is_non_interactive_session() -> bool:
    return not _STATE["is_interactive"]


def get_is_interactive() -> bool:
    return _STATE["is_interactive"]


def set_is_interactive(value: bool) -> None:
    _STATE["is_interactive"] = value


def get_client_type() -> str:
    return _STATE["client_type"]


def set_client_type(client_type: str) -> None:
    _STATE["client_type"] = client_type


def get_sdk_agent_progress_summaries_enabled() -> bool:
    return _STATE["sdk_agent_progress_summaries_enabled"]


def set_sdk_agent_progress_summaries_enabled(value: bool) -> None:
    _STATE["sdk_agent_progress_summaries_enabled"] = value


def get_kairos_active() -> bool:
    return _STATE["kairos_active"]


def set_kairos_active(value: bool) -> None:
    _STATE["kairos_active"] = value


def get_strict_tool_result_pairing() -> bool:
    return _STATE["strict_tool_result_pairing"]


def set_strict_tool_result_pairing(value: bool) -> None:
    _STATE["strict_tool_result_pairing"] = value


def get_user_msg_opt_in() -> bool:
    return _STATE["user_msg_opt_in"]


def set_user_msg_opt_in(value: bool) -> None:
    _STATE["user_msg_opt_in"] = value


def get_session_source() -> Optional[str]:
    return _STATE["session_source"]


def set_session_source(source: str) -> None:
    _STATE["session_source"] = source


def get_question_preview_format() -> Optional[str]:
    return _STATE["question_preview_format"]


def set_question_preview_format(fmt: str) -> None:
    _STATE["question_preview_format"] = fmt


def get_agent_color_map() -> dict:
    return _STATE["agent_color_map"]


# ---------------------------------------------------------------------------
# Flag settings / settings sources
# ---------------------------------------------------------------------------

def get_flag_settings_path() -> Optional[str]:
    return _STATE["flag_settings_path"]


def set_flag_settings_path(path: Optional[str]) -> None:
    _STATE["flag_settings_path"] = path


def get_flag_settings_inline() -> Optional[dict]:
    return _STATE["flag_settings_inline"]


def set_flag_settings_inline(settings: Optional[dict]) -> None:
    _STATE["flag_settings_inline"] = settings


def get_session_ingress_token() -> Optional[str]:
    return _STATE["session_ingress_token"]


def set_session_ingress_token(token: Optional[str]) -> None:
    _STATE["session_ingress_token"] = token


def get_oauth_token_from_fd() -> Optional[str]:
    return _STATE["oauth_token_from_fd"]


def set_oauth_token_from_fd(token: Optional[str]) -> None:
    _STATE["oauth_token_from_fd"] = token


def get_api_key_from_fd() -> Optional[str]:
    return _STATE["api_key_from_fd"]


def set_api_key_from_fd(key: Optional[str]) -> None:
    _STATE["api_key_from_fd"] = key


def set_last_api_request(params: Optional[dict]) -> None:
    _STATE["last_api_request"] = params


def get_last_api_request() -> Optional[dict]:
    return _STATE["last_api_request"]


def set_last_api_request_messages(messages: Optional[list]) -> None:
    _STATE["last_api_request_messages"] = messages


def get_last_api_request_messages() -> Optional[list]:
    return _STATE["last_api_request_messages"]


def set_last_classifier_requests(requests: Optional[list]) -> None:
    _STATE["last_classifier_requests"] = requests


def get_last_classifier_requests() -> Optional[list]:
    return _STATE["last_classifier_requests"]


def set_cached_claude_md_content(content: Optional[str]) -> None:
    _STATE["cached_claude_md_content"] = content


def get_cached_claude_md_content() -> Optional[str]:
    return _STATE["cached_claude_md_content"]


def add_to_in_memory_error_log(error_info: dict) -> None:
    MAX_IN_MEMORY_ERRORS = 100
    if len(_STATE["in_memory_error_log"]) >= MAX_IN_MEMORY_ERRORS:
        _STATE["in_memory_error_log"].pop(0)
    _STATE["in_memory_error_log"].append(error_info)


def get_allowed_setting_sources() -> list:
    return _STATE["allowed_setting_sources"]


def set_allowed_setting_sources(sources: list) -> None:
    _STATE["allowed_setting_sources"] = sources


def prefer_third_party_authentication() -> bool:
    return get_is_non_interactive_session() and _STATE["client_type"] != "claude-vscode"


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------

def set_inline_plugins(plugins: list) -> None:
    _STATE["inline_plugins"] = plugins


def get_inline_plugins() -> list:
    return _STATE["inline_plugins"]


def set_chrome_flag_override(value: Optional[bool]) -> None:
    _STATE["chrome_flag_override"] = value


def get_chrome_flag_override() -> Optional[bool]:
    return _STATE["chrome_flag_override"]


def set_use_cowork_plugins(value: bool) -> None:
    _STATE["use_cowork_plugins"] = value
    try:
        from ..utils.settings.settings_cache import reset_settings_cache
        reset_settings_cache()
    except ImportError:
        pass


def get_use_cowork_plugins() -> bool:
    return _STATE["use_cowork_plugins"]


# ---------------------------------------------------------------------------
# Session-only permission flags
# ---------------------------------------------------------------------------

def set_session_bypass_permissions_mode(enabled: bool) -> None:
    _STATE["session_bypass_permissions_mode"] = enabled


def get_session_bypass_permissions_mode() -> bool:
    return _STATE["session_bypass_permissions_mode"]


def set_scheduled_tasks_enabled(enabled: bool) -> None:
    _STATE["scheduled_tasks_enabled"] = enabled


def get_scheduled_tasks_enabled() -> bool:
    return _STATE["scheduled_tasks_enabled"]


# ---------------------------------------------------------------------------
# Session cron tasks
# ---------------------------------------------------------------------------

def get_session_cron_tasks() -> list:
    return _STATE["session_cron_tasks"]


def add_session_cron_task(task: SessionCronTask) -> None:
    _STATE["session_cron_tasks"].append(task)


def remove_session_cron_tasks(ids: list) -> int:
    if not ids:
        return 0
    id_set = set(ids)
    before = len(_STATE["session_cron_tasks"])
    _STATE["session_cron_tasks"] = [t for t in _STATE["session_cron_tasks"] if t["id"] not in id_set]
    return before - len(_STATE["session_cron_tasks"])


# ---------------------------------------------------------------------------
# Session trust / persistence
# ---------------------------------------------------------------------------

def set_session_trust_accepted(accepted: bool) -> None:
    _STATE["session_trust_accepted"] = accepted


def get_session_trust_accepted() -> bool:
    return _STATE["session_trust_accepted"]


def set_session_persistence_disabled(disabled: bool) -> None:
    _STATE["session_persistence_disabled"] = disabled


def is_session_persistence_disabled() -> bool:
    return _STATE["session_persistence_disabled"]


# ---------------------------------------------------------------------------
# Plan / auto mode transitions
# ---------------------------------------------------------------------------

def has_exited_plan_mode_in_session() -> bool:
    return _STATE["has_exited_plan_mode"]


def set_has_exited_plan_mode(value: bool) -> None:
    _STATE["has_exited_plan_mode"] = value


def needs_plan_mode_exit_attachment() -> bool:
    return _STATE["needs_plan_mode_exit_attachment"]


def set_needs_plan_mode_exit_attachment(value: bool) -> None:
    _STATE["needs_plan_mode_exit_attachment"] = value


def handle_plan_mode_transition(from_mode: str, to_mode: str) -> None:
    if to_mode == "plan" and from_mode != "plan":
        _STATE["needs_plan_mode_exit_attachment"] = False
    if from_mode == "plan" and to_mode != "plan":
        _STATE["needs_plan_mode_exit_attachment"] = True


def needs_auto_mode_exit_attachment() -> bool:
    return _STATE["needs_auto_mode_exit_attachment"]


def set_needs_auto_mode_exit_attachment(value: bool) -> None:
    _STATE["needs_auto_mode_exit_attachment"] = value


def handle_auto_mode_transition(from_mode: str, to_mode: str) -> None:
    if (from_mode == "auto" and to_mode == "plan") or (from_mode == "plan" and to_mode == "auto"):
        return
    from_is_auto = from_mode == "auto"
    to_is_auto = to_mode == "auto"
    if to_is_auto and not from_is_auto:
        _STATE["needs_auto_mode_exit_attachment"] = False
    if from_is_auto and not to_is_auto:
        _STATE["needs_auto_mode_exit_attachment"] = True


# ---------------------------------------------------------------------------
# LSP recommendation
# ---------------------------------------------------------------------------

def has_shown_lsp_recommendation_this_session() -> bool:
    return _STATE["lsp_recommendation_shown_this_session"]


def set_lsp_recommendation_shown_this_session(value: bool) -> None:
    _STATE["lsp_recommendation_shown_this_session"] = value


# ---------------------------------------------------------------------------
# SDK init state / hooks
# ---------------------------------------------------------------------------

def set_init_json_schema(schema: dict) -> None:
    _STATE["init_json_schema"] = schema


def get_init_json_schema() -> Optional[dict]:
    return _STATE["init_json_schema"]


def register_hook_callbacks(hooks: dict) -> None:
    if _STATE["registered_hooks"] is None:
        _STATE["registered_hooks"] = {}
    for event, matchers in hooks.items():
        if event not in _STATE["registered_hooks"]:
            _STATE["registered_hooks"][event] = []
        _STATE["registered_hooks"][event].extend(matchers)


def get_registered_hooks() -> Optional[dict]:
    return _STATE["registered_hooks"]


def clear_registered_hooks() -> None:
    _STATE["registered_hooks"] = None


def clear_registered_plugin_hooks() -> None:
    if not _STATE["registered_hooks"]:
        return
    filtered = {}
    for event, matchers in _STATE["registered_hooks"].items():
        callback_hooks = [m for m in matchers if "plugin_root" not in m]
        if callback_hooks:
            filtered[event] = callback_hooks
    _STATE["registered_hooks"] = filtered if filtered else None


def reset_sdk_init_state() -> None:
    _STATE["init_json_schema"] = None
    _STATE["registered_hooks"] = None


# ---------------------------------------------------------------------------
# Plan slug cache
# ---------------------------------------------------------------------------

def get_plan_slug_cache() -> dict:
    return _STATE["plan_slug_cache"]


# ---------------------------------------------------------------------------
# Session created teams
# ---------------------------------------------------------------------------

def get_session_created_teams() -> set:
    return _STATE["session_created_teams"]


# ---------------------------------------------------------------------------
# Teleported session
# ---------------------------------------------------------------------------

def set_teleported_session_info(session_id: Optional[str]) -> None:
    _STATE["teleported_session_info"] = {
        "is_teleported": True,
        "has_logged_first_message": False,
        "session_id": session_id,
    }


def get_teleported_session_info() -> Optional[dict]:
    return _STATE["teleported_session_info"]


def mark_first_teleport_message_logged() -> None:
    if _STATE["teleported_session_info"]:
        _STATE["teleported_session_info"]["has_logged_first_message"] = True


# ---------------------------------------------------------------------------
# Invoked skills
# ---------------------------------------------------------------------------

def add_invoked_skill(
    skill_name: str,
    skill_path: str,
    content: str,
    agent_id: Optional[str] = None,
) -> None:
    key = f"{agent_id or ''}:{skill_name}"
    _STATE["invoked_skills"][key] = {
        "skill_name": skill_name,
        "skill_path": skill_path,
        "content": content,
        "invoked_at": _now_ms(),
        "agent_id": agent_id,
    }


def get_invoked_skills() -> dict:
    return _STATE["invoked_skills"]


def get_invoked_skills_for_agent(agent_id: Optional[str]) -> dict:
    normalized = agent_id
    return {k: v for k, v in _STATE["invoked_skills"].items() if v["agent_id"] == normalized}


def clear_invoked_skills(preserved_agent_ids: Optional[set] = None) -> None:
    if not preserved_agent_ids:
        _STATE["invoked_skills"].clear()
        return
    to_delete = [
        k for k, v in _STATE["invoked_skills"].items()
        if v["agent_id"] is None or v["agent_id"] not in preserved_agent_ids
    ]
    for k in to_delete:
        del _STATE["invoked_skills"][k]


def clear_invoked_skills_for_agent(agent_id: str) -> None:
    to_delete = [k for k, v in _STATE["invoked_skills"].items() if v["agent_id"] == agent_id]
    for k in to_delete:
        del _STATE["invoked_skills"][k]


# ---------------------------------------------------------------------------
# Slow operations (ant-only dev bar)
# ---------------------------------------------------------------------------

_MAX_SLOW_OPERATIONS = 10
_SLOW_OPERATION_TTL_MS = 10000
_EMPTY_SLOW_OPERATIONS: list = []


def add_slow_operation(operation: str, duration_ms: int) -> None:
    if os.environ.get("USER_TYPE") != "ant":
        return
    if "exec" in operation and "claude-prompt-" in operation:
        return
    now = _now_ms()
    _STATE["slow_operations"] = [
        op for op in _STATE["slow_operations"]
        if now - op["timestamp"] < _SLOW_OPERATION_TTL_MS
    ]
    _STATE["slow_operations"].append({"operation": operation, "duration_ms": duration_ms, "timestamp": now})
    if len(_STATE["slow_operations"]) > _MAX_SLOW_OPERATIONS:
        _STATE["slow_operations"] = _STATE["slow_operations"][-_MAX_SLOW_OPERATIONS:]


def get_slow_operations() -> list:
    if not _STATE["slow_operations"]:
        return _EMPTY_SLOW_OPERATIONS
    now = _now_ms()
    if any(now - op["timestamp"] >= _SLOW_OPERATION_TTL_MS for op in _STATE["slow_operations"]):
        _STATE["slow_operations"] = [
            op for op in _STATE["slow_operations"]
            if now - op["timestamp"] < _SLOW_OPERATION_TTL_MS
        ]
        if not _STATE["slow_operations"]:
            return _EMPTY_SLOW_OPERATIONS
    return _STATE["slow_operations"]


# ---------------------------------------------------------------------------
# Main thread agent type / remote mode
# ---------------------------------------------------------------------------

def get_main_thread_agent_type() -> Optional[str]:
    return _STATE["main_thread_agent_type"]


def set_main_thread_agent_type(agent_type: Optional[str]) -> None:
    _STATE["main_thread_agent_type"] = agent_type


def get_is_remote_mode() -> bool:
    return _STATE["is_remote_mode"]


def set_is_remote_mode(value: bool) -> None:
    _STATE["is_remote_mode"] = value


# ---------------------------------------------------------------------------
# System prompt section cache
# ---------------------------------------------------------------------------

def get_system_prompt_section_cache() -> dict:
    return _STATE["system_prompt_section_cache"]


def set_system_prompt_section_cache_entry(name: str, value: Optional[str]) -> None:
    _STATE["system_prompt_section_cache"][name] = value


def clear_system_prompt_section_state() -> None:
    _STATE["system_prompt_section_cache"].clear()


# ---------------------------------------------------------------------------
# Last emitted date
# ---------------------------------------------------------------------------

def get_last_emitted_date() -> Optional[str]:
    return _STATE["last_emitted_date"]


def set_last_emitted_date(date: Optional[str]) -> None:
    _STATE["last_emitted_date"] = date


# ---------------------------------------------------------------------------
# Additional directories for CLAUDE.md
# ---------------------------------------------------------------------------

def get_additional_directories_for_claude_md() -> list:
    return _STATE["additional_directories_for_claude_md"]


def set_additional_directories_for_claude_md(directories: list) -> None:
    _STATE["additional_directories_for_claude_md"] = directories


# ---------------------------------------------------------------------------
# Allowed channels
# ---------------------------------------------------------------------------

def get_allowed_channels() -> list:
    return _STATE["allowed_channels"]


def set_allowed_channels(entries: list) -> None:
    _STATE["allowed_channels"] = entries


def get_has_dev_channels() -> bool:
    return _STATE["has_dev_channels"]


def set_has_dev_channels(value: bool) -> None:
    _STATE["has_dev_channels"] = value


# ---------------------------------------------------------------------------
# Prompt cache 1h
# ---------------------------------------------------------------------------

def get_prompt_cache_1h_allowlist() -> Optional[list]:
    return _STATE["prompt_cache_1h_allowlist"]


def set_prompt_cache_1h_allowlist(allowlist: Optional[list]) -> None:
    _STATE["prompt_cache_1h_allowlist"] = allowlist


def get_prompt_cache_1h_eligible() -> Optional[bool]:
    return _STATE["prompt_cache_1h_eligible"]


def set_prompt_cache_1h_eligible(eligible: Optional[bool]) -> None:
    _STATE["prompt_cache_1h_eligible"] = eligible


# ---------------------------------------------------------------------------
# Beta header latches
# ---------------------------------------------------------------------------

def get_afk_mode_header_latched() -> Optional[bool]:
    return _STATE["afk_mode_header_latched"]


def set_afk_mode_header_latched(v: bool) -> None:
    _STATE["afk_mode_header_latched"] = v


def get_fast_mode_header_latched() -> Optional[bool]:
    return _STATE["fast_mode_header_latched"]


def set_fast_mode_header_latched(v: bool) -> None:
    _STATE["fast_mode_header_latched"] = v


def get_cache_editing_header_latched() -> Optional[bool]:
    return _STATE["cache_editing_header_latched"]


def set_cache_editing_header_latched(v: bool) -> None:
    _STATE["cache_editing_header_latched"] = v


def get_thinking_clear_latched() -> Optional[bool]:
    return _STATE["thinking_clear_latched"]


def set_thinking_clear_latched(v: bool) -> None:
    _STATE["thinking_clear_latched"] = v


def clear_beta_header_latches() -> None:
    """Reset beta header latches to None. Called on /clear and /compact."""
    _STATE["afk_mode_header_latched"] = None
    _STATE["fast_mode_header_latched"] = None
    _STATE["cache_editing_header_latched"] = None
    _STATE["thinking_clear_latched"] = None


# ---------------------------------------------------------------------------
# Prompt ID
# ---------------------------------------------------------------------------

def get_prompt_id() -> Optional[str]:
    return _STATE["prompt_id"]


def set_prompt_id(id_: Optional[str]) -> None:
    _STATE["prompt_id"] = id_
