"""
In-process teammate spawning.

Creates and registers an in-process teammate task. Unlike process-based
teammates (tmux/iTerm2), in-process teammates run in the same Python process
using context variables for isolation.

This module handles:
1. Creating TeammateContext
2. Creating linked AbortController
3. Registering InProcessTeammateTaskState in AppState
4. Returning spawn result for backend

原始 TS: utils/swarm/spawnInProcess.ts
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..debug import log_for_debugging
from .team_helpers import remove_member_by_agent_id

SetAppStateFn = Callable[[Callable[[Any], Any]], None]


@dataclass
class SpawnContext:
    """Minimal context required for spawning an in-process teammate."""

    set_app_state: SetAppStateFn
    tool_use_id: Optional[str] = None


@dataclass
class InProcessSpawnConfig:
    """Configuration for spawning an in-process teammate."""

    name: str
    """Display name for the teammate, e.g., 'researcher'"""

    team_name: str
    """Team this teammate belongs to"""

    prompt: str
    """Initial prompt/task for the teammate"""

    plan_mode_required: bool
    """Whether teammate must enter plan mode before implementing"""

    color: Optional[str] = None
    """Optional UI color for the teammate"""

    model: Optional[str] = None
    """Optional model override for this teammate"""


@dataclass
class InProcessSpawnOutput:
    """Result from spawning an in-process teammate."""

    success: bool
    """Whether spawn was successful"""

    agent_id: str
    """Full agent ID (format: 'name@team')"""

    task_id: Optional[str] = None
    """Task ID for tracking in AppState"""

    abort_controller: Optional[Any] = None
    """AbortController for this teammate (linked to parent)"""

    teammate_context: Optional[Any] = None
    """Teammate context for isolation"""

    error: Optional[str] = None
    """Error message if spawn failed"""


def _generate_task_id(task_type: str) -> str:
    """Generate a unique task ID."""
    try:
        from ...task import generate_task_id
        return generate_task_id(task_type)
    except (ImportError, Exception):
        ts = int(time.time() * 1000)
        rnd = random.randint(0, 999999)
        return f"{task_type}-{ts}-{rnd}"


def _create_abort_controller() -> Any:
    """Create an abort controller."""
    try:
        from ..abort_controller import create_abort_controller
        return create_abort_controller()
    except (ImportError, Exception):
        try:
            from ..abort import create_abort_controller as _create
            return _create()
        except (ImportError, Exception):
            # Minimal fallback
            class _SimpleAbortController:
                def __init__(self) -> None:
                    self._aborted = False
                    self._reason: Any = None

                def abort(self, reason: Any = None) -> None:
                    self._aborted = True
                    self._reason = reason

                @property
                def signal(self) -> "_SimpleAbortSignal":
                    return _SimpleAbortSignal(self)

            class _SimpleAbortSignal:
                def __init__(self, ctrl: "_SimpleAbortController") -> None:
                    self._ctrl = ctrl

                @property
                def aborted(self) -> bool:
                    return self._ctrl._aborted

                @property
                def reason(self) -> Any:
                    return self._ctrl._reason

                def add_event_listener(self, *args: Any, **kwargs: Any) -> None:
                    pass

            return _SimpleAbortController()


async def spawn_in_process_teammate(
    config: InProcessSpawnConfig,
    context: SpawnContext,
) -> InProcessSpawnOutput:
    """Spawn an in-process teammate.

    Creates the teammate's context, registers the task in AppState, and returns
    the spawn result. The actual agent execution is driven by the
    InProcessTeammateTask component which uses run_with_teammate_context() to
    execute the agent loop with proper identity isolation.

    Args:
        config: Spawn configuration.
        context: Context with set_app_state for registering task.

    Returns:
        Spawn result with teammate info.
    """
    name = config.name
    team_name = config.team_name
    prompt = config.prompt
    color = config.color
    plan_mode_required = config.plan_mode_required
    model = config.model
    set_app_state = context.set_app_state

    # Generate deterministic agent ID
    try:
        from ...tools.shared.spawn_multi_agent import format_agent_id
        agent_id = format_agent_id(name, team_name)
    except (ImportError, Exception):
        agent_id = f"{name}@{team_name}"

    task_id = _generate_task_id("in_process_teammate")

    log_for_debugging(
        f"[spawn_in_process_teammate] Spawning {agent_id} (taskId: {task_id})"
    )

    try:
        # Create independent AbortController for this teammate
        abort_controller = _create_abort_controller()

        # Get parent session ID for transcript correlation
        parent_session_id: Optional[str] = None
        try:
            from ...bootstrap.state import get_session_id
            parent_session_id = get_session_id()
        except (ImportError, Exception):
            pass

        # Create teammate context for isolation
        teammate_context: Optional[Any] = None
        try:
            from ..teammate_context import create_teammate_context
            teammate_context = create_teammate_context(
                agent_id=agent_id,
                agent_name=name,
                team_name=team_name,
                color=color,
                plan_mode_required=plan_mode_required,
                parent_session_id=parent_session_id,
                abort_controller=abort_controller,
            )
        except (ImportError, Exception) as e:
            log_for_debugging(f"[spawn_in_process_teammate] Could not create teammate context: {e}")

        # Register agent in Perfetto trace if enabled
        try:
            from ..telemetry.perfetto_tracing import (
                is_perfetto_tracing_enabled,
                register_agent as register_perfetto_agent,
            )
            if is_perfetto_tracing_enabled() and parent_session_id:
                register_perfetto_agent(agent_id, name, parent_session_id)
        except (ImportError, Exception):
            pass

        # Build task description
        truncated_prompt = prompt[:50] + ("..." if len(prompt) > 50 else "")
        description = f"{name}: {truncated_prompt}"

        # Build task state
        task_state: Dict[str, Any] = {
            "id": task_id,
            "type": "in_process_teammate",
            "status": "running",
            "description": description,
            "toolUseId": context.tool_use_id,
            "identity": {
                "agentId": agent_id,
                "agentName": name,
                "teamName": team_name,
                "color": color,
                "planModeRequired": plan_mode_required,
                "parentSessionId": parent_session_id,
            },
            "prompt": prompt,
            "model": model,
            "abortController": abort_controller,
            "awaitingPlanApproval": False,
            "permissionMode": "plan" if plan_mode_required else "default",
            "isIdle": False,
            "shutdownRequested": False,
            "lastReportedToolCount": 0,
            "lastReportedTokenCount": 0,
            "pendingUserMessages": [],
            "messages": [],
            "createdAt": int(time.time() * 1000),
        }

        # Register cleanup handler for graceful shutdown
        def _cleanup() -> None:
            log_for_debugging(f"[spawn_in_process_teammate] Cleanup called for {agent_id}")
            abort_controller.abort()

        unregister_cleanup: Optional[Callable[[], None]] = None
        try:
            from ..cleanup_registry import register_cleanup
            unregister_cleanup = register_cleanup(_cleanup)
            task_state["unregisterCleanup"] = unregister_cleanup
        except (ImportError, Exception):
            pass

        # Register task in AppState
        def _register(prev: Any) -> Any:
            tasks = dict(getattr(prev, "tasks", {}) or (prev.get("tasks", {}) if isinstance(prev, dict) else {}))
            tasks[task_id] = task_state
            if isinstance(prev, dict):
                return {**prev, "tasks": tasks}
            # dataclass-like
            try:
                import copy
                new_state = copy.copy(prev)
                new_state.tasks = tasks
                return new_state
            except Exception:
                return prev

        set_app_state(_register)

        log_for_debugging(
            f"[spawn_in_process_teammate] Registered {agent_id} in AppState"
        )

        return InProcessSpawnOutput(
            success=True,
            agent_id=agent_id,
            task_id=task_id,
            abort_controller=abort_controller,
            teammate_context=teammate_context,
        )

    except Exception as e:
        error_message = str(e) if e else "Unknown error during spawn"
        log_for_debugging(
            f"[spawn_in_process_teammate] Failed to spawn {agent_id}: {error_message}"
        )
        return InProcessSpawnOutput(
            success=False,
            agent_id=agent_id,
            error=error_message,
        )


def kill_in_process_teammate(
    task_id: str,
    set_app_state: SetAppStateFn,
) -> bool:
    """Kill an in-process teammate by aborting its controller.

    Note: This is the implementation called by InProcessBackend.kill().

    Args:
        task_id: Task ID of the teammate to kill.
        set_app_state: AppState setter.

    Returns:
        True if killed successfully.
    """
    killed = False
    team_name_ref: Optional[str] = None
    agent_id_ref: Optional[str] = None
    tool_use_id_ref: Optional[str] = None
    description_ref: Optional[str] = None

    def _updater(prev: Any) -> Any:
        nonlocal killed, team_name_ref, agent_id_ref, tool_use_id_ref, description_ref

        if isinstance(prev, dict):
            tasks = prev.get("tasks", {})
        else:
            tasks = getattr(prev, "tasks", {}) or {}

        task = tasks.get(task_id)
        if not task:
            return prev

        # Support both dict and object task state
        def _get(t: Any, key: str, default: Any = None) -> Any:
            if isinstance(t, dict):
                return t.get(key, default)
            return getattr(t, key, default)

        if _get(task, "type") != "in_process_teammate":
            return prev

        if _get(task, "status") != "running":
            return prev

        # Capture identity for cleanup
        identity = _get(task, "identity", {})
        if isinstance(identity, dict):
            team_name_ref = identity.get("teamName")
            agent_id_ref = identity.get("agentId")
        else:
            team_name_ref = getattr(identity, "teamName", None)
            agent_id_ref = getattr(identity, "agentId", None)

        tool_use_id_ref = _get(task, "toolUseId")
        description_ref = _get(task, "description")

        # Abort the controller
        abort_ctrl = _get(task, "abortController")
        if abort_ctrl:
            try:
                abort_ctrl.abort()
            except Exception:
                pass

        # Call cleanup handler
        unregister_cleanup = _get(task, "unregisterCleanup")
        if unregister_cleanup:
            try:
                unregister_cleanup()
            except Exception:
                pass

        # Call idle callbacks
        on_idle_callbacks = _get(task, "onIdleCallbacks", []) or []
        for cb in on_idle_callbacks:
            try:
                cb()
            except Exception:
                pass

        killed = True

        # Build updated task state
        if isinstance(task, dict):
            updated_task = {
                **task,
                "status": "killed",
                "notified": True,
                "endTime": int(time.time() * 1000),
                "onIdleCallbacks": [],
                "pendingUserMessages": [],
                "inProgressToolUseIDs": None,
                "abortController": None,
                "unregisterCleanup": None,
                "currentWorkAbortController": None,
            }
            messages = task.get("messages", []) or []
            updated_task["messages"] = [messages[-1]] if messages else None
        else:
            updated_task = task
            # Minimal attribute update
            try:
                task.status = "killed"
                task.notified = True
                task.endTime = int(time.time() * 1000)
            except Exception:
                pass

        # Update team context teammates
        if isinstance(prev, dict):
            team_context = prev.get("teamContext")
            if team_context and agent_id_ref:
                if isinstance(team_context, dict):
                    teammates = dict(team_context.get("teammates", {}))
                    teammates.pop(agent_id_ref, None)
                    team_context = {**team_context, "teammates": teammates}

            updated_tasks = {**tasks, task_id: updated_task}
            return {**prev, "tasks": updated_tasks, "teamContext": team_context}
        else:
            try:
                import copy
                new_state = copy.copy(prev)
                new_tasks = dict(tasks)
                new_tasks[task_id] = updated_task
                new_state.tasks = new_tasks
                if agent_id_ref:
                    team_ctx = getattr(new_state, "teamContext", None)
                    if team_ctx:
                        if isinstance(team_ctx, dict):
                            teammates = dict(team_ctx.get("teammates", {}))
                            teammates.pop(agent_id_ref, None)
                            new_state.teamContext = {**team_ctx, "teammates": teammates}
                return new_state
            except Exception:
                return prev

    set_app_state(_updater)

    # Remove from team file (outside state updater to avoid file I/O in callback)
    if team_name_ref and agent_id_ref:
        remove_member_by_agent_id(team_name_ref, agent_id_ref)

    if killed:
        # Evict task output asynchronously
        import asyncio
        try:
            from ..task.disk_output import evict_task_output
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(evict_task_output(task_id))
                else:
                    loop.run_until_complete(evict_task_output(task_id))
            except Exception:
                pass
        except (ImportError, Exception):
            pass

        # Emit task terminated SDK event
        try:
            from ..sdk_event_queue import emit_task_terminated_sdk
            emit_task_terminated_sdk(
                task_id,
                "stopped",
                tool_use_id=tool_use_id_ref,
                summary=description_ref,
            )
        except (ImportError, Exception):
            pass

        # Schedule eviction of terminal task
        STOPPED_DISPLAY_MS = 2000

        def _evict() -> None:
            try:
                from ..task.framework import evict_terminal_task
                evict_terminal_task(task_id, set_app_state)
            except (ImportError, Exception):
                pass

        import threading
        timer = threading.Timer(STOPPED_DISPLAY_MS / 1000.0, _evict)
        timer.daemon = True
        timer.start()

    # Release perfetto agent registry entry
    if agent_id_ref:
        try:
            from ..telemetry.perfetto_tracing import unregister_agent as unregister_perfetto_agent
            unregister_perfetto_agent(agent_id_ref)
        except (ImportError, Exception):
            pass

    return killed
