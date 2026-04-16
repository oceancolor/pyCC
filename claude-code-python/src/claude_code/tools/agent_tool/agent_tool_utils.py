"""
agent_tool_utils.py — AgentTool utilities.
Ported from AgentTool/agentToolUtils.ts (686 lines).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Tool name constants
# ---------------------------------------------------------------------------

AGENT_TOOL_NAME = "Task"
EXIT_PLAN_MODE_V2_TOOL_NAME = "exit_plan_mode"

# Tools always disallowed for sub-agents
ALL_AGENT_DISALLOWED_TOOLS: Set[str] = frozenset([
    "exit_plan_mode",
])

# Tools disallowed for custom (non-built-in) agents
CUSTOM_AGENT_DISALLOWED_TOOLS: Set[str] = frozenset([])

# Tools allowed for async agents
ASYNC_AGENT_ALLOWED_TOOLS: Set[str] = frozenset([
    "Bash", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep",
    "LS", "Task", "WebSearch", "WebFetch", "TodoRead", "TodoWrite",
    "NotebookRead", "NotebookEdit",
])

# Tools allowed for in-process teammates
IN_PROCESS_TEAMMATE_ALLOWED_TOOLS: Set[str] = frozenset([
    "TodoRead", "TodoWrite",
])


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class ResolvedAgentTools:
    has_wildcard: bool
    valid_tools: List[str]
    invalid_tools: List[str]
    resolved_tools: List[Any]
    allowed_agent_types: Optional[List[str]] = None


@dataclass
class AgentToolResult:
    agent_id: str
    agent_type: str
    content: List[Dict[str, Any]]
    total_duration_ms: int
    total_tokens: int
    total_tool_use_count: int
    usage: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper flags (stub implementations)
# ---------------------------------------------------------------------------

def is_agent_swarms_enabled() -> bool:
    """Check if agent swarms feature is enabled."""
    import os
    return os.environ.get("CLAUDE_AGENT_SWARMS", "").lower() in ("1", "true")


def is_in_process_teammate() -> bool:
    """Check if running as an in-process teammate."""
    import os
    return os.environ.get("CLAUDE_IN_PROCESS_TEAMMATE", "").lower() in ("1", "true")


def tool_matches_name(tool: Any, name: str) -> bool:
    """Check if a tool matches a given name."""
    if isinstance(tool, dict):
        return tool.get("name") == name
    return getattr(tool, "name", None) == name


def permission_rule_value_from_string(spec: str) -> Tuple[str, Optional[str]]:
    """Parse 'ToolName(rule_content)' → (tool_name, rule_content)."""
    if "(" in spec and spec.endswith(")"):
        idx = spec.index("(")
        return spec[:idx].strip(), spec[idx + 1:-1].strip()
    return spec.strip(), None


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def filter_tools_for_agent(
    tools: List[Any],
    is_built_in: bool,
    is_async: bool = False,
    permission_mode: str = "default",
) -> List[Any]:
    """
    Filter the tool pool for a sub-agent.
    Mirrors filterToolsForAgent() in agentToolUtils.ts.
    """
    result = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", "")

        # Allow MCP tools for all agents
        if name.startswith("mcp__"):
            result.append(tool)
            continue

        # Allow ExitPlanMode in plan mode
        if name == EXIT_PLAN_MODE_V2_TOOL_NAME and permission_mode == "plan":
            result.append(tool)
            continue

        if name in ALL_AGENT_DISALLOWED_TOOLS:
            continue

        if not is_built_in and name in CUSTOM_AGENT_DISALLOWED_TOOLS:
            continue

        if is_async and name not in ASYNC_AGENT_ALLOWED_TOOLS:
            if is_agent_swarms_enabled() and is_in_process_teammate():
                if name == AGENT_TOOL_NAME:
                    result.append(tool)
                    continue
                if name in IN_PROCESS_TEAMMATE_ALLOWED_TOOLS:
                    result.append(tool)
                    continue
            continue

        result.append(tool)
    return result


def resolve_agent_tools(
    agent_definition: Any,
    available_tools: List[Any],
    is_async: bool = False,
    is_main_thread: bool = False,
) -> ResolvedAgentTools:
    """
    Resolve and validate agent tools against available tools.
    Handles wildcard expansion and validation.
    Mirrors resolveAgentTools() in agentToolUtils.ts.
    """
    if isinstance(agent_definition, dict):
        agent_tools = agent_definition.get("tools")
        disallowed_tools = agent_definition.get("disallowed_tools") or []
        source = agent_definition.get("source", "custom")
        permission_mode = agent_definition.get("permission_mode", "default")
    else:
        agent_tools = getattr(agent_definition, "tools", None)
        disallowed_tools = getattr(agent_definition, "disallowed_tools", None) or []
        source = getattr(agent_definition, "source", "custom")
        permission_mode = getattr(agent_definition, "permission_mode", "default")

    # Filter available tools (skip for main thread)
    if is_main_thread:
        filtered_available = list(available_tools)
    else:
        filtered_available = filter_tools_for_agent(
            available_tools,
            is_built_in=(source == "built-in"),
            is_async=is_async,
            permission_mode=permission_mode,
        )

    # Build disallowed set
    disallowed_set: Set[str] = set()
    for spec in disallowed_tools:
        tool_name, _ = permission_rule_value_from_string(spec)
        disallowed_set.add(tool_name)

    allowed_available = [
        t for t in filtered_available
        if (t.get("name") if isinstance(t, dict) else getattr(t, "name", "")) not in disallowed_set
    ]

    # Wildcard check
    has_wildcard = (
        agent_tools is None
        or (len(agent_tools) == 1 and agent_tools[0] == "*")
    )
    if has_wildcard:
        return ResolvedAgentTools(
            has_wildcard=True,
            valid_tools=[],
            invalid_tools=[],
            resolved_tools=allowed_available,
        )

    # Build lookup map
    available_map: Dict[str, Any] = {}
    for tool in allowed_available:
        name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", "")
        available_map[name] = tool

    valid_tools: List[str] = []
    invalid_tools: List[str] = []
    resolved: List[Any] = []
    resolved_set: Set[str] = set()
    allowed_agent_types: Optional[List[str]] = None

    for spec in agent_tools:
        tool_name, rule_content = permission_rule_value_from_string(spec)

        if tool_name == AGENT_TOOL_NAME:
            if rule_content:
                allowed_agent_types = [s.strip() for s in rule_content.split(",")]
            if not is_main_thread:
                valid_tools.append(spec)
                continue

        tool = available_map.get(tool_name)
        if tool is not None:
            valid_tools.append(spec)
            if tool_name not in resolved_set:
                resolved.append(tool)
                resolved_set.add(tool_name)
        else:
            invalid_tools.append(spec)

    return ResolvedAgentTools(
        has_wildcard=False,
        valid_tools=valid_tools,
        invalid_tools=invalid_tools,
        resolved_tools=resolved,
        allowed_agent_types=allowed_agent_types,
    )


def count_tool_uses(messages: List[Any]) -> int:
    """Count total tool_use blocks across assistant messages."""
    count = 0
    for msg in messages:
        if isinstance(msg, dict):
            if msg.get("type") != "assistant":
                continue
            content = msg.get("message", {}).get("content", [])
        else:
            if getattr(msg, "type", None) != "assistant":
                continue
            message = getattr(msg, "message", None)
            content = getattr(message, "content", []) if message else []

        for block in content:
            block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if block_type == "tool_use":
                count += 1
    return count


def get_last_tool_use_name(message: Any) -> Optional[str]:
    """Return the name of the last tool_use block in an assistant message."""
    if isinstance(message, dict):
        if message.get("type") != "assistant":
            return None
        content = message.get("message", {}).get("content", [])
    else:
        if getattr(message, "type", None) != "assistant":
            return None
        msg = getattr(message, "message", None)
        content = getattr(msg, "content", []) if msg else []

    last_name = None
    for block in content:
        block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if block_type == "tool_use":
            last_name = block.get("name") if isinstance(block, dict) else getattr(block, "name", None)
    return last_name


def finalize_agent_tool(
    agent_messages: List[Any],
    agent_id: str,
    metadata: Dict[str, Any],
) -> AgentToolResult:
    """
    Build the final AgentToolResult from completed agent messages.
    Mirrors finalizeAgentTool() in agentToolUtils.ts.
    """
    start_time = metadata.get("start_time", 0)
    agent_type = metadata.get("agent_type", "custom")

    # Find last assistant message with text content
    content: List[Dict[str, Any]] = []
    usage: Dict[str, Any] = {}
    total_tokens = 0

    for msg in reversed(agent_messages):
        if isinstance(msg, dict):
            if msg.get("type") != "assistant":
                continue
            msg_content = msg.get("message", {}).get("content", [])
            msg_usage = msg.get("message", {}).get("usage", {})
        else:
            if getattr(msg, "type", None) != "assistant":
                continue
            message = getattr(msg, "message", None)
            msg_content = getattr(message, "content", []) if message else []
            msg_usage = getattr(message, "usage", {}) if message else {}

        text_blocks = [
            b for b in msg_content
            if (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "text"
        ]
        if text_blocks:
            content = [
                {"type": "text", "text": b.get("text") if isinstance(b, dict) else getattr(b, "text", "")}
                for b in text_blocks
            ]
            usage = msg_usage if isinstance(msg_usage, dict) else {}
            total_tokens = (
                usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            )
            break

    total_tool_use_count = count_tool_uses(agent_messages)
    duration_ms = int((time.time() * 1000) - start_time) if start_time else 0

    return AgentToolResult(
        agent_id=agent_id,
        agent_type=agent_type,
        content=content,
        total_duration_ms=duration_ms,
        total_tokens=total_tokens,
        total_tool_use_count=total_tool_use_count,
        usage=usage,
    )


def extract_partial_result(messages: List[Any]) -> Optional[str]:
    """
    Extract partial text result from in-progress agent messages.
    Returns None if no text content found.
    """
    for msg in reversed(messages):
        if isinstance(msg, dict):
            if msg.get("type") != "assistant":
                continue
            content = msg.get("message", {}).get("content", [])
        else:
            if getattr(msg, "type", None) != "assistant":
                continue
            message = getattr(msg, "message", None)
            content = getattr(message, "content", []) if message else []

        for block in content:
            block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if block_type == "text":
                return block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
    return None


async def run_async_agent_lifecycle(
    agent_id: str,
    run_fn: Callable,
    on_complete: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
) -> Any:
    """
    Run an agent lifecycle asynchronously.
    Mirrors runAsyncAgentLifecycle() in agentToolUtils.ts.
    """
    try:
        result = await run_fn()
        if on_complete:
            if asyncio.iscoroutinefunction(on_complete):
                await on_complete(result)
            else:
                on_complete(result)
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        if on_error:
            if asyncio.iscoroutinefunction(on_error):
                await on_error(e)
            else:
                on_error(e)
        raise


async def classify_handoff_if_needed(
    agent_messages: List[Any],
    tools: List[Any],
    tool_permission_context: Any = None,
    abort_signal: Any = None,
    subagent_type: str = "custom",
    total_tool_use_count: int = 0,
) -> Optional[str]:
    """
    Classify if the agent result represents a handoff to another agent.
    Mirrors classifyHandoffIfNeeded() in agentToolUtils.ts.
    Returns classification string or None.
    """
    # Stub: return None (no handoff) by default
    return None


def emit_task_progress(
    tracker: Any,
    task_id: str,
    tool_use_id: Optional[str],
    description: str,
    start_time: float,
    last_tool_name: str,
) -> None:
    """
    Emit task progress event.
    Mirrors emitTaskProgress() in agentToolUtils.ts.
    """
    # Stub: log only
    import logging
    logging.getLogger(__name__).debug(
        "Task progress: task_id=%s tool=%s description=%s",
        task_id, last_tool_name, description[:80],
    )


def generate_agent_id(prefix: str = "agent") -> str:
    """Generate a unique agent ID."""
    return f"{prefix}:{uuid.uuid4()}"
