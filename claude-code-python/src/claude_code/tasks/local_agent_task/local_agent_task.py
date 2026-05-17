"""LocalAgentTask. Ported from tasks/LocalAgentTask/LocalAgentTask.tsx."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Progress tracking types (mirrors TS ToolActivity / AgentProgress)
# ---------------------------------------------------------------------------

@dataclass
class ToolActivity:
    """A single tool-use activity from the agent."""
    tool_name: str
    input: Dict[str, Any] = field(default_factory=dict)
    activity_description: Optional[str] = None
    is_search: Optional[bool] = None
    is_read: Optional[bool] = None


@dataclass
class AgentProgress:
    """Current progress state for a running agent task."""
    tool_use_count: int = 0
    token_count: int = 0
    last_activity: Optional[ToolActivity] = None
    recent_activities: List[ToolActivity] = field(default_factory=list)
    summary: Optional[str] = None


MAX_RECENT_ACTIVITIES = 5


@dataclass
class ProgressTracker:
    """Mutable tracker accumulating progress from streamed messages."""
    tool_use_count: int = 0
    # input_tokens is cumulative per turn in the Claude API — keep the latest value.
    latest_input_tokens: int = 0
    # output_tokens is per-turn — sum these.
    cumulative_output_tokens: int = 0
    recent_activities: List[ToolActivity] = field(default_factory=list)


def create_progress_tracker() -> ProgressTracker:
    return ProgressTracker()


def get_token_count_from_tracker(tracker: ProgressTracker) -> int:
    return tracker.latest_input_tokens + tracker.cumulative_output_tokens


def update_progress_from_message(
    tracker: ProgressTracker,
    message: Any,
    resolve_activity_description: Optional[Callable] = None,
    tools: Any = None,
) -> None:
    """
    Update *tracker* in place from a single streamed assistant message.
    Mirrors ``updateProgressFromMessage`` from LocalAgentTask.tsx.
    """
    # Only process assistant messages
    msg_type = message.get("type") if isinstance(message, dict) else getattr(message, "type", None)
    if msg_type != "assistant":
        return

    inner = message.get("message", {}) if isinstance(message, dict) else getattr(message, "message", {})
    usage = (inner or {}).get("usage", {}) if isinstance(inner, dict) else getattr(inner, "usage", {})

    input_tokens = (usage.get("input_tokens", 0) if isinstance(usage, dict) else getattr(usage, "input_tokens", 0))
    cache_creation = (usage.get("cache_creation_input_tokens", 0) if isinstance(usage, dict) else
                      getattr(usage, "cache_creation_input_tokens", 0))
    cache_read = (usage.get("cache_read_input_tokens", 0) if isinstance(usage, dict) else
                  getattr(usage, "cache_read_input_tokens", 0))
    output_tokens = (usage.get("output_tokens", 0) if isinstance(usage, dict) else
                     getattr(usage, "output_tokens", 0))

    tracker.latest_input_tokens = (input_tokens or 0) + (cache_creation or 0) + (cache_read or 0)
    tracker.cumulative_output_tokens += (output_tokens or 0)

    content = (inner or {}).get("content", []) if isinstance(inner, dict) else getattr(inner, "content", [])
    for block in (content or []):
        block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if block_type != "tool_use":
            continue

        # Skip the synthetic output tool
        tool_name = block.get("name", "") if isinstance(block, dict) else getattr(block, "name", "")
        try:
            from claude_code.tools.synthetic_output_tool.synthetic_output_tool import (  # type: ignore[import]
                SYNTHETIC_OUTPUT_TOOL_NAME,
            )
            if tool_name == SYNTHETIC_OUTPUT_TOOL_NAME:
                continue
        except ImportError:
            pass

        tracker.tool_use_count += 1
        inp = block.get("input", {}) if isinstance(block, dict) else getattr(block, "input", {})

        # Resolve activity description
        description: Optional[str] = None
        if resolve_activity_description and callable(resolve_activity_description):
            try:
                description = resolve_activity_description(tool_name, inp or {})
            except Exception:
                pass

        # Classify search / read
        is_search: Optional[bool] = None
        is_read: Optional[bool] = None
        if tools is not None:
            try:
                from claude_code.utils.collapse_read_search import (  # type: ignore[import]
                    get_tool_search_or_read_info,
                )
                info = get_tool_search_or_read_info(tool_name, inp or {}, tools)
                if info:
                    is_search = info.get("is_search")
                    is_read = info.get("is_read")
            except (ImportError, Exception):
                pass

        tracker.recent_activities.append(
            ToolActivity(
                tool_name=tool_name,
                input=inp or {},
                activity_description=description,
                is_search=is_search,
                is_read=is_read,
            )
        )

    # Cap the rolling window
    while len(tracker.recent_activities) > MAX_RECENT_ACTIVITIES:
        tracker.recent_activities.pop(0)


def get_progress_update(tracker: ProgressTracker) -> AgentProgress:
    """Snapshot the current tracker state as an AgentProgress."""
    last = tracker.recent_activities[-1] if tracker.recent_activities else None
    return AgentProgress(
        tool_use_count=tracker.tool_use_count,
        token_count=get_token_count_from_tracker(tracker),
        last_activity=last,
        recent_activities=list(tracker.recent_activities),
    )


def create_activity_description_resolver(tools: Any) -> Callable:
    """
    Build an ``ActivityDescriptionResolver`` from a tools list.
    Mirrors ``createActivityDescriptionResolver``.
    """
    def _resolve(tool_name: str, inp: Dict[str, Any]) -> Optional[str]:
        try:
            from claude_code.tool import find_tool_by_name  # type: ignore[import]
            tool = find_tool_by_name(tools, tool_name)
            if tool is not None:
                get_desc = getattr(tool, "get_activity_description", None)
                if callable(get_desc):
                    return get_desc(inp)
        except (ImportError, Exception):
            pass
        return None
    return _resolve


# ---------------------------------------------------------------------------
# LocalAgentTaskState
# ---------------------------------------------------------------------------

@dataclass
class LocalAgentTaskState:
    """
    State for a local agent sub-task.
    Mirrors ``LocalAgentTaskState`` from LocalAgentTask.tsx.
    """
    id: str
    type: str = "local_agent"
    status: str = "pending"
    description: str = ""
    agent_id: str = ""
    prompt: str = ""
    agent_type: str = "subagent"
    model: Optional[str] = None
    abort_controller: Optional[Any] = None
    unregister_cleanup: Optional[Callable] = None
    error: Optional[str] = None
    result: Optional[Any] = None
    progress: Optional[AgentProgress] = None
    retrieved: bool = False
    messages: Optional[List[Any]] = None
    last_reported_tool_count: int = 0
    last_reported_token_count: int = 0
    is_backgrounded: bool = True
    pending_messages: List[str] = field(default_factory=list)
    retain: bool = False
    disk_loaded: bool = False
    evict_after: Optional[float] = None
    selected_agent: Optional[Any] = None
    tool_use_id: Optional[str] = None
    start_time: float = field(default_factory=lambda: time.time() * 1000)
    end_time: Optional[float] = None
    notified: bool = False
    output_file: str = ""
    output_offset: int = 0


def is_local_agent_task(task: Any) -> bool:
    """Return True if *task* is a LocalAgentTaskState."""
    if isinstance(task, dict):
        return task.get("type") == "local_agent"
    return getattr(task, "type", None) == "local_agent"


# ---------------------------------------------------------------------------
# Task descriptor
# ---------------------------------------------------------------------------

class LocalAgentTask:
    """
    Task descriptor for local agent sub-tasks.
    Mirrors the exported ``LocalAgentTask`` Task object from LocalAgentTask.tsx.
    """
    type = "local_agent"
    name = "LocalAgentTask"

    @classmethod
    async def kill(cls, task_id: str, set_app_state: Callable) -> None:
        """
        Kill a running LocalAgentTask.

        Aborts the abort controller and marks status as 'killed'.
        Mirrors ``LocalAgentTask.kill`` from the TS source.
        """
        tool_use_id: Optional[str] = None
        description: Optional[str] = None
        killed = False

        def _update(prev: dict) -> dict:
            nonlocal tool_use_id, description, killed
            tasks = dict(prev.get("tasks") or {})
            task = tasks.get(task_id)
            if task is None:
                return prev

            if isinstance(task, LocalAgentTaskState):
                if task.status != "running":
                    return prev
                tool_use_id = task.tool_use_id
                description = task.description
                ac = task.abort_controller
                if ac and hasattr(ac, "abort"):
                    try:
                        ac.abort()
                    except Exception:
                        pass
                if task.unregister_cleanup:
                    try:
                        task.unregister_cleanup()
                    except Exception:
                        pass
                killed = True
                tasks[task_id] = LocalAgentTaskState(
                    **{**task.__dict__,
                       "status": "killed",
                       "end_time": time.time() * 1000,
                       "notified": True,
                       "abort_controller": None,
                       "unregister_cleanup": None}
                )
            elif isinstance(task, dict):
                if task.get("status") != "running":
                    return prev
                tool_use_id = task.get("tool_use_id")
                description = task.get("description")
                ac = task.get("abort_controller")
                if ac and hasattr(ac, "abort"):
                    try:
                        ac.abort()
                    except Exception:
                        pass
                unregister = task.get("unregister_cleanup")
                if callable(unregister):
                    try:
                        unregister()
                    except Exception:
                        pass
                killed = True
                tasks[task_id] = {**task, "status": "killed",
                                  "end_time": time.time() * 1000,
                                  "notified": True, "abort_controller": None,
                                  "unregister_cleanup": None}
            return {**prev, "tasks": tasks}

        set_app_state(_update)

        if killed:
            # Evict task disk output
            try:
                from claude_code.utils.task.disk_output import evict_task_output  # type: ignore[import]
                asyncio.ensure_future(evict_task_output(task_id))
            except (ImportError, Exception):
                pass

            # Emit SDK task-terminated event
            try:
                from claude_code.utils.sdk_event_queue import emit_task_terminated_sdk  # type: ignore[import]
                emit_task_terminated_sdk(
                    task_id,
                    "stopped",
                    tool_use_id=tool_use_id,
                    summary=description,
                )
            except (ImportError, Exception):
                pass
