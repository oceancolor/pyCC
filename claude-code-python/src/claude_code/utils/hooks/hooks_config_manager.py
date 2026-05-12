"""
Hooks config manager - group and query hooks configuration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .hooks_settings import get_all_hooks, sort_matchers_by_priority


HOOK_EVENT_METADATA: Dict[str, Dict[str, Any]] = {
    "PreToolUse": {
        "summary": "Before tool execution",
        "description": "Input to command is JSON of tool call arguments.",
        "matcherMetadata": {"fieldToMatch": "tool_name", "values": []},
    },
    "PostToolUse": {
        "summary": "After tool execution",
        "description": "Input to command is JSON with fields 'inputs' and 'response'.",
        "matcherMetadata": {"fieldToMatch": "tool_name", "values": []},
    },
    "PostToolUseFailure": {
        "summary": "After tool execution fails",
        "description": "Input to command is JSON with tool_name, tool_input, tool_use_id, error.",
        "matcherMetadata": {"fieldToMatch": "tool_name", "values": []},
    },
    "PermissionDenied": {
        "summary": "After auto mode classifier denies a tool call",
        "description": "Input to command is JSON with tool_name, tool_input, tool_use_id, and reason.",
        "matcherMetadata": {"fieldToMatch": "tool_name", "values": []},
    },
    "Notification": {
        "summary": "When notifications are sent",
        "description": "Input to command is JSON with notification message and type.",
        "matcherMetadata": {
            "fieldToMatch": "notification_type",
            "values": ["permission_prompt", "idle_prompt", "auth_success"],
        },
    },
    "UserPromptSubmit": {
        "summary": "When the user submits a prompt",
        "description": "Input to command is JSON with original user prompt text.",
    },
    "SessionStart": {
        "summary": "When a new session is started",
        "description": "Input to command is JSON with session start source.",
        "matcherMetadata": {
            "fieldToMatch": "source",
            "values": ["startup", "resume", "clear", "compact"],
        },
    },
    "SessionEnd": {
        "summary": "When a session is ending",
        "description": "Input to command is JSON with session end reason.",
        "matcherMetadata": {
            "fieldToMatch": "reason",
            "values": ["clear", "logout", "prompt_input_exit", "other"],
        },
    },
    "Stop": {
        "summary": "Right before Claude concludes its response",
        "description": "Exit code 0 - stdout/stderr not shown",
    },
    "StopFailure": {
        "summary": "When the turn ends due to an API error",
        "description": "Fires instead of Stop when an API error ended the turn.",
        "matcherMetadata": {
            "fieldToMatch": "error",
            "values": ["rate_limit", "authentication_failed", "billing_error"],
        },
    },
    "SubagentStart": {
        "summary": "When a subagent is started",
        "description": "Input to command is JSON with agent_id and agent_type.",
        "matcherMetadata": {"fieldToMatch": "agent_type", "values": []},
    },
    "SubagentStop": {
        "summary": "Right before a subagent concludes its response",
        "description": "Input to command is JSON with agent_id, agent_type, and agent_transcript_path.",
        "matcherMetadata": {"fieldToMatch": "agent_type", "values": []},
    },
    "PreCompact": {
        "summary": "Before conversation compaction",
        "description": "Input to command is JSON with compaction details.",
        "matcherMetadata": {"fieldToMatch": "trigger", "values": ["manual", "auto"]},
    },
    "PostCompact": {
        "summary": "After conversation compaction",
        "description": "Input to command is JSON with compaction details and summary.",
        "matcherMetadata": {"fieldToMatch": "trigger", "values": ["manual", "auto"]},
    },
    "PermissionRequest": {
        "summary": "When a permission dialog is displayed",
        "description": "Input to command is JSON with tool_name, tool_input, and tool_use_id.",
        "matcherMetadata": {"fieldToMatch": "tool_name", "values": []},
    },
    "Setup": {
        "summary": "Repo setup hooks for init and maintenance",
        "description": "Input to command is JSON with trigger (init or maintenance).",
        "matcherMetadata": {"fieldToMatch": "trigger", "values": ["init", "maintenance"]},
    },
    "TeammateIdle": {
        "summary": "When a teammate is about to go idle",
        "description": "Input to command is JSON with teammate_name and team_name.",
    },
    "TaskCreated": {
        "summary": "When a task is being created",
        "description": "Input to command is JSON with task details.",
    },
    "TaskCompleted": {
        "summary": "When a task is being marked as completed",
        "description": "Input to command is JSON with task details.",
    },
    "Elicitation": {
        "summary": "When an MCP server requests user input",
        "description": "Input to command is JSON with mcp_server_name, message, and requested_schema.",
        "matcherMetadata": {"fieldToMatch": "mcp_server_name", "values": []},
    },
    "ElicitationResult": {
        "summary": "After a user responds to an MCP elicitation",
        "description": "Input to command is JSON with mcp_server_name, action, content.",
        "matcherMetadata": {"fieldToMatch": "mcp_server_name", "values": []},
    },
    "ConfigChange": {
        "summary": "When configuration files change during a session",
        "description": "Input to command is JSON with source and file_path.",
        "matcherMetadata": {
            "fieldToMatch": "source",
            "values": ["user_settings", "project_settings", "local_settings"],
        },
    },
    "InstructionsLoaded": {
        "summary": "When an instruction file is loaded",
        "description": "Input to command is JSON with file_path and memory_type.",
        "matcherMetadata": {
            "fieldToMatch": "load_reason",
            "values": ["session_start", "nested_traversal", "path_glob_match"],
        },
    },
    "WorktreeCreate": {
        "summary": "Create an isolated worktree",
        "description": "Input to command is JSON with name.",
    },
    "WorktreeRemove": {
        "summary": "Remove a previously created worktree",
        "description": "Input to command is JSON with worktree_path.",
    },
    "CwdChanged": {
        "summary": "After the working directory changes",
        "description": "Input to command is JSON with old_cwd and new_cwd.",
    },
    "FileChanged": {
        "summary": "When a watched file changes",
        "description": "Input to command is JSON with file_path and event.",
    },
}


def get_hook_event_metadata(tool_names: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """Return hook event metadata, optionally populated with tool names."""
    tool_names = tool_names or []
    result = {}
    for event, meta in HOOK_EVENT_METADATA.items():
        entry = dict(meta)
        if "matcherMetadata" in entry and entry["matcherMetadata"].get("fieldToMatch") == "tool_name":
            matcher_meta = dict(entry["matcherMetadata"])
            matcher_meta["values"] = tool_names
            entry["matcherMetadata"] = matcher_meta
        result[event] = entry
    return result


def group_hooks_by_event_and_matcher(
    app_state: Any,
    tool_names: Optional[List[str]] = None,
) -> Dict[str, Dict[str, List[Any]]]:
    """Group hooks by event and matcher."""
    tool_names = tool_names or []
    grouped: Dict[str, Dict[str, List[Any]]] = {
        event: {} for event in HOOK_EVENT_METADATA
    }

    metadata = get_hook_event_metadata(tool_names)
    for hook in get_all_hooks(app_state):
        event = hook.get("event", "")
        event_group = grouped.get(event)
        if event_group is not None:
            has_matcher_meta = metadata.get(event, {}).get("matcherMetadata") is not None
            matcher_key = hook.get("matcher", "") if has_matcher_meta else ""
            event_group.setdefault(matcher_key, []).append(hook)

    return grouped


def get_sorted_matchers_for_event(
    hooks_by_event_and_matcher: Dict[str, Dict[str, List[Any]]],
    event: str,
) -> List[str]:
    """Get sorted matchers for a specific event."""
    matchers = list(hooks_by_event_and_matcher.get(event, {}).keys())
    return sort_matchers_by_priority(matchers, hooks_by_event_and_matcher, event)


def get_hooks_for_matcher(
    hooks_by_event_and_matcher: Dict[str, Dict[str, List[Any]]],
    event: str,
    matcher: Optional[str],
) -> List[Any]:
    """Get hooks for a specific event and matcher."""
    matcher_key = matcher if matcher is not None else ""
    return hooks_by_event_and_matcher.get(event, {}).get(matcher_key, [])


def get_matcher_metadata(event: str, tool_names: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific event's matcher."""
    return get_hook_event_metadata(tool_names or []).get(event, {}).get("matcherMetadata")
