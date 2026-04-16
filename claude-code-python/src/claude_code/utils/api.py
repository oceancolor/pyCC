"""
Python port of utils/api.ts (718 lines)

Provides:
  - SystemPromptBlock dataclass
  - normalize_api_tool_name()
  - get_tools_for_api()
  - get_system_prompt() / split_sys_prompt_prefix()
  - append_system_context() / prepend_user_context()
  - normalize_tool_input() / normalize_tool_input_for_api()

Analytics / growthbook calls are stubbed (return False / None).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Stubs for analytics / feature-flags (no-ops in Python port)
# ---------------------------------------------------------------------------

def _check_statsig_feature_gate(gate: str) -> bool:          # noqa: D401
    """Stub: always returns False (feature gates disabled in Python port)."""
    return False


def _get_feature_value(key: str, default: Any = None) -> Any:  # noqa: D401
    """Stub: always returns *default*."""
    return default


def _is_analytics_disabled() -> bool:
    return True


def _should_use_global_cache_scope() -> bool:
    """Stub: global cache scope not available in Python port."""
    return False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Boundary marker separating static from dynamic system-prompt content.
SYSTEM_PROMPT_DYNAMIC_BOUNDARY = "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"

# CLI system-prompt prefixes that get 'org' cache scope treatment.
# In the TS version this is a Set imported from constants/system.ts.
CLI_SYSPROMPT_PREFIXES: set[str] = set()

# Tool names where swarm-specific fields should be filtered when swarms are off.
EXIT_PLAN_MODE_V2_TOOL_NAME = "exit_plan_mode"
AGENT_TOOL_NAME = "agent"
TASK_OUTPUT_TOOL_NAME = "task_output"

SWARM_FIELDS_BY_TOOL: Dict[str, List[str]] = {
    EXIT_PLAN_MODE_V2_TOOL_NAME: ["launchSwarm", "teammateCount"],
    AGENT_TOOL_NAME: ["name", "team_name", "mode"],
}

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

CacheScope = Literal["global", "org"]


@dataclass
class SystemPromptBlock:
    """A single block of system-prompt text with its cache scope."""
    text: str
    cache_scope: Optional[CacheScope]  # None means no cache_control


# SystemPrompt is just a list of strings (may include empty strings).
SystemPrompt = List[str]


@dataclass
class APITool:
    """Minimal representation of a tool as sent to the Anthropic API."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    strict: Optional[bool] = None
    defer_loading: Optional[bool] = None
    eager_input_streaming: Optional[bool] = None
    cache_control: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# normalize_api_tool_name
# ---------------------------------------------------------------------------

_TOOL_NAME_ILLEGAL = re.compile(r"[^a-zA-Z0-9_-]")


def normalize_api_tool_name(name: str) -> str:
    """Replace characters illegal in Anthropic tool names with underscores.

    Tool names must match ``^[a-zA-Z0-9_-]+$``.
    """
    return _TOOL_NAME_ILLEGAL.sub("_", name)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _filter_swarm_fields_from_schema(
    tool_name: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    """Remove swarm-related fields from a tool's input_schema when swarms are off."""
    fields_to_remove = SWARM_FIELDS_BY_TOOL.get(tool_name)
    if not fields_to_remove:
        return schema

    filtered = dict(schema)
    props = filtered.get("properties")
    if props and isinstance(props, dict):
        filtered_props = dict(props)
        for f in fields_to_remove:
            filtered_props.pop(f, None)
        filtered["properties"] = filtered_props
    return filtered


def _is_agent_swarms_enabled() -> bool:
    """Stub: swarms are disabled by default in Python port."""
    return os.environ.get("CLAUDE_CODE_AGENT_SWARMS_ENABLED", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# get_tools_for_api
# ---------------------------------------------------------------------------

def get_tools_for_api(
    tools: Sequence[Any],
    is_swarms_enabled: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Convert a list of Tool objects into the format expected by the Anthropic API.

    Each tool in *tools* should expose:
      - ``name: str``
      - ``description: str``   (or an async ``prompt()`` method — not awaited here)
      - ``input_schema: dict`` or ``input_json_schema: dict``

    The function performs:
    1. Name normalisation (``normalize_api_tool_name``)
    2. Swarm-field filtering (when swarms disabled)
    3. Returns a list of plain dicts ready for the ``tools=`` API parameter.
    """
    if is_swarms_enabled is None:
        is_swarms_enabled = _is_agent_swarms_enabled()

    result: List[Dict[str, Any]] = []
    for tool in tools:
        name: str = getattr(tool, "name", "") or ""
        api_name = normalize_api_tool_name(name)

        # Prefer pre-built JSON schema, fall back to any schema dict attribute.
        schema: Dict[str, Any] = (
            getattr(tool, "input_json_schema", None)
            or getattr(tool, "inputJSONSchema", None)
            or getattr(tool, "input_schema", None)
            or {"type": "object", "properties": {}}
        )
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}

        # Filter swarm fields when feature is disabled.
        if not is_swarms_enabled:
            schema = _filter_swarm_fields_from_schema(name, schema)

        # Description: use attribute or fall back to empty string.
        description: str = getattr(tool, "description", "") or ""

        api_tool: Dict[str, Any] = {
            "name": api_name,
            "description": description,
            "input_schema": schema,
        }

        # Optional extras
        if getattr(tool, "strict", None):
            api_tool["strict"] = True
        if getattr(tool, "is_mcp", False):
            api_tool["_is_mcp"] = True  # internal marker, stripped before sending

        result.append(api_tool)
    return result


# ---------------------------------------------------------------------------
# split_sys_prompt_prefix / get_system_prompt
# ---------------------------------------------------------------------------

def split_sys_prompt_prefix(
    system_prompt: SystemPrompt,
    *,
    skip_global_cache_for_system_prompt: bool = False,
) -> List[SystemPromptBlock]:
    """Split a flat system-prompt list into cacheable blocks.

    Mirrors the TS ``splitSysPromptPrefix`` logic, simplified for Python:

    * Global cache scope (``shouldUseGlobalCacheScope``) is stubbed to False.
    * Without global cache, returns up to 3 blocks:
        1. Attribution header (``cacheScope=None``)
        2. System-prompt prefix block (``cacheScope='org'``)
        3. Everything else joined with ``\\n\\n`` (``cacheScope='org'``)
    """
    use_global = _should_use_global_cache_scope()

    if use_global and skip_global_cache_for_system_prompt:
        # Org-level only, drop boundary marker
        attribution: Optional[str] = None
        prefix: Optional[str] = None
        rest_parts: List[str] = []

        for block in system_prompt:
            if not block:
                continue
            if block == SYSTEM_PROMPT_DYNAMIC_BOUNDARY:
                continue
            if block.startswith("x-anthropic-billing-header"):
                attribution = block
            elif block in CLI_SYSPROMPT_PREFIXES:
                prefix = block
            else:
                rest_parts.append(block)

        result: List[SystemPromptBlock] = []
        if attribution:
            result.append(SystemPromptBlock(text=attribution, cache_scope=None))
        if prefix:
            result.append(SystemPromptBlock(text=prefix, cache_scope="org"))
        joined_rest = "\n\n".join(rest_parts)
        if joined_rest:
            result.append(SystemPromptBlock(text=joined_rest, cache_scope="org"))
        return result

    if use_global:
        try:
            boundary_idx = system_prompt.index(SYSTEM_PROMPT_DYNAMIC_BOUNDARY)
        except ValueError:
            boundary_idx = -1

        if boundary_idx != -1:
            attribution = None
            prefix = None
            static_parts: List[str] = []
            dynamic_parts: List[str] = []

            for i, block in enumerate(system_prompt):
                if not block or block == SYSTEM_PROMPT_DYNAMIC_BOUNDARY:
                    continue
                if block.startswith("x-anthropic-billing-header"):
                    attribution = block
                elif block in CLI_SYSPROMPT_PREFIXES:
                    prefix = block
                elif i < boundary_idx:
                    static_parts.append(block)
                else:
                    dynamic_parts.append(block)

            out: List[SystemPromptBlock] = []
            if attribution:
                out.append(SystemPromptBlock(text=attribution, cache_scope=None))
            if prefix:
                out.append(SystemPromptBlock(text=prefix, cache_scope=None))
            static_joined = "\n\n".join(static_parts)
            if static_joined:
                out.append(SystemPromptBlock(text=static_joined, cache_scope="global"))
            dynamic_joined = "\n\n".join(dynamic_parts)
            if dynamic_joined:
                out.append(SystemPromptBlock(text=dynamic_joined, cache_scope=None))
            return out

    # Default / fallback: up to 3 blocks with 'org' scope.
    attribution = None
    prefix = None
    rest_parts = []

    for block in system_prompt:
        if not block:
            continue
        if block.startswith("x-anthropic-billing-header"):
            attribution = block
        elif block in CLI_SYSPROMPT_PREFIXES:
            prefix = block
        else:
            rest_parts.append(block)

    result = []
    if attribution:
        result.append(SystemPromptBlock(text=attribution, cache_scope=None))
    if prefix:
        result.append(SystemPromptBlock(text=prefix, cache_scope="org"))
    joined_rest = "\n\n".join(rest_parts)
    if joined_rest:
        result.append(SystemPromptBlock(text=joined_rest, cache_scope="org"))
    return result


def get_system_prompt(
    tools: Sequence[Any],
    system_prompt_parts: SystemPrompt,
    *,
    skip_global_cache: bool = False,
) -> List[SystemPromptBlock]:
    """Build the API-ready system-prompt block list.

    Convenience wrapper around ``split_sys_prompt_prefix`` that accepts both
    tool list and prompt parts.  The *tools* parameter is currently unused in
    the Python port (tool-count-based cache logic is handled upstream); it is
    kept for API compatibility with the TS original.

    Returns a list of :class:`SystemPromptBlock` ready for ``cache_control``
    injection before the API call.
    """
    return split_sys_prompt_prefix(
        system_prompt_parts,
        skip_global_cache_for_system_prompt=skip_global_cache,
    )


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def append_system_context(
    system_prompt: SystemPrompt,
    context: Dict[str, str],
) -> List[str]:
    """Append a key-value context dict as an additional system prompt block."""
    context_text = "\n".join(f"{k}: {v}" for k, v in context.items())
    return [b for b in [*system_prompt, context_text] if b]


def prepend_user_context(
    messages: List[Dict[str, Any]],
    context: Dict[str, str],
    *,
    is_test: bool = False,
) -> List[Dict[str, Any]]:
    """Prepend a system-reminder user message containing context key-value pairs.

    Mirrors the TS ``prependUserContext`` function.  In test mode (or when
    *context* is empty) returns *messages* unchanged.
    """
    if is_test or not context:
        return messages

    context_lines = "\n".join(f"# {k}\n{v}" for k, v in context.items())
    reminder = (
        "<system-reminder>\n"
        "As you answer the user's questions, you can use the following context:\n"
        f"{context_lines}\n\n"
        "IMPORTANT: this context may or may not be relevant to your tasks. "
        "You should not respond to this context unless it is highly relevant to your task.\n"
        "</system-reminder>\n"
    )
    meta_message: Dict[str, Any] = {
        "role": "user",
        "content": reminder,
        "_is_meta": True,
    }
    return [meta_message, *messages]


# ---------------------------------------------------------------------------
# normalize_tool_input / normalize_tool_input_for_api
# ---------------------------------------------------------------------------

def normalize_tool_input(
    tool_name: str,
    input_data: Dict[str, Any],
    *,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalise tool input before execution.

    Ported from the TS ``normalizeToolInput``.  Currently handles:
    - ``BashTool``: strips leading ``cd <cwd> && `` prefix, replaces ``\\\\;`` → ``\\;``.
    - ``FileWriteTool``: strips trailing whitespace from non-markdown files.
    - All others: returned unchanged.
    """
    if tool_name == "Bash":
        cmd: str = input_data.get("command", "")
        effective_cwd = cwd or os.getcwd()
        # Strip common ``cd <cwd> && `` prefix that Claude sometimes prepends.
        prefix_posix = f"cd {effective_cwd} && "
        if cmd.startswith(prefix_posix):
            cmd = cmd[len(prefix_posix):]
        # Replace \\; with \; (for find -exec compatibility)
        cmd = cmd.replace("\\\\;", "\\;")
        return {**input_data, "command": cmd}

    if tool_name == "Write":
        file_path: str = input_data.get("file_path", "")
        content: str = input_data.get("content", "")
        is_markdown = file_path.lower().endswith((".md", ".mdx"))
        if not is_markdown:
            # Strip trailing whitespace from each line.
            lines = content.split("\n")
            content = "\n".join(line.rstrip() for line in lines)
        return {**input_data, "content": content}

    return input_data


def normalize_tool_input_for_api(
    tool_name: str,
    input_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Strip fields injected by ``normalize_tool_input`` before sending to API.

    Mirrors the TS ``normalizeToolInputForAPI``.
    """
    if tool_name == EXIT_PLAN_MODE_V2_TOOL_NAME:
        return {k: v for k, v in input_data.items() if k not in ("plan", "planFilePath")}

    if tool_name == "Edit":
        # Strip legacy whole-file fields if new-style ``edits`` list is present.
        if "edits" in input_data:
            return {
                k: v for k, v in input_data.items()
                if k not in ("old_string", "new_string", "replace_all")
            }
        return input_data

    return input_data


# ---------------------------------------------------------------------------
# Tool-to-API-schema conversion (async version for callers that need it)
# ---------------------------------------------------------------------------

async def tool_to_api_schema(
    tool: Any,
    *,
    cache_control: Optional[Dict[str, Any]] = None,
    defer_loading: bool = False,
) -> Dict[str, Any]:
    """Convert a single Tool to its API dict, optionally with cache_control.

    For tools that expose an async ``prompt()`` method the description is
    awaited.  Falls back to the ``description`` attribute otherwise.
    """
    name = normalize_api_tool_name(getattr(tool, "name", ""))
    # Resolve description (may be async)
    desc_attr = getattr(tool, "description", "")
    if callable(desc_attr):
        try:
            import asyncio
            if asyncio.iscoroutinefunction(desc_attr):
                description = await desc_attr()
            else:
                description = desc_attr()
        except Exception:  # noqa: BLE001
            description = ""
    else:
        description = desc_attr or ""

    schema: Dict[str, Any] = (
        getattr(tool, "input_json_schema", None)
        or getattr(tool, "input_schema", None)
        or {"type": "object", "properties": {}}
    )

    if not _is_agent_swarms_enabled():
        schema = _filter_swarm_fields_from_schema(getattr(tool, "name", ""), schema)

    api_tool: Dict[str, Any] = {
        "name": name,
        "description": description,
        "input_schema": schema,
    }

    if getattr(tool, "strict", None):
        api_tool["strict"] = True

    if defer_loading:
        api_tool["defer_loading"] = True

    if cache_control:
        api_tool["cache_control"] = cache_control

    # Honour kill-switch: strip experimental beta fields.
    if os.environ.get("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", "").lower() in ("1", "true"):
        allowed = {"name", "description", "input_schema", "cache_control"}
        api_tool = {k: v for k, v in api_tool.items() if k in allowed}

    return api_tool
