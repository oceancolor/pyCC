"""Conversation clearing utility. Ported from commands/clear/conversation.ts"""
from __future__ import annotations

import asyncio
import logging
import uuid as _uuid_module
from typing import TYPE_CHECKING, Any, Callable, Optional, Set

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from claude_code.types.message import Message


async def clear_conversation(
    set_messages: Optional[Callable] = None,
    read_file_state: Any = None,
    discovered_skill_names: Optional[Set[str]] = None,
    loaded_nested_memory_paths: Optional[Set[str]] = None,
    get_app_state: Optional[Callable] = None,
    set_app_state: Optional[Callable] = None,
    set_conversation_id: Optional[Callable] = None,
) -> None:
    """
    Clear the conversation, reset session state, and fire session hooks.

    Mirrors the TypeScript ``clearConversation`` function in
    ``commands/clear/conversation.ts``.

    Steps:
      1. Execute SessionEnd hooks (bounded timeout).
      2. Log a cache-eviction hint for the last request.
      3. Compute preserved background tasks before wiping state.
      4. Reset messages (``set_messages(() => [])``).
      5. Force a new conversation ID (``set_conversation_id(new_uuid)``).
      6. Clear all session caches (excluding preserved background agent IDs).
      7. Reset cwd / file-state cache / skill / memory path sets.
      8. Clean app state (tasks, attribution, mcp, etc.).
      9. Clear plan slug cache + session metadata.
     10. Regenerate session ID.
     11. Execute SessionStart hooks and inject resulting messages.

    Parameters
    ----------
    set_messages:
        ``(updater: Callable[[list], list]) -> None`` — update the message list.
    read_file_state:
        File-state cache with a ``clear()`` method.
    discovered_skill_names:
        Mutable set of skill names to clear.
    loaded_nested_memory_paths:
        Mutable set of memory paths to clear.
    get_app_state:
        ``() -> AppState`` — read-only snapshot of app state.
    set_app_state:
        ``(updater: Callable[[AppState], AppState]) -> None`` — update app state.
    set_conversation_id:
        ``(id: str) -> None`` — force logo/UI re-render with a new conversation ID.
    """
    # ------------------------------------------------------------------
    # 1. SessionEnd hooks
    # ------------------------------------------------------------------
    try:
        from claude_code.utils.hooks import (  # type: ignore[import]
            execute_session_end_hooks,
            get_session_end_hook_timeout_ms,
        )
        timeout_ms = get_session_end_hook_timeout_ms()
        await asyncio.wait_for(
            execute_session_end_hooks(
                "clear",
                get_app_state=get_app_state,
                set_app_state=set_app_state,
            ),
            timeout=timeout_ms / 1000,
        )
    except (ImportError, asyncio.TimeoutError, Exception) as exc:
        logger.debug("SessionEnd hook skipped: %s", exc)

    # ------------------------------------------------------------------
    # 2. Cache-eviction hint
    # ------------------------------------------------------------------
    try:
        from claude_code.bootstrap.state import get_last_main_request_id  # type: ignore[import]
        from claude_code.services.analytics import log_event  # type: ignore[import]

        last_request_id = get_last_main_request_id()
        if last_request_id:
            log_event(
                "tengu_cache_eviction_hint",
                {
                    "scope": "conversation_clear",
                    "last_request_id": last_request_id,
                },
            )
    except (ImportError, Exception) as exc:
        logger.debug("Cache eviction hint skipped: %s", exc)

    # ------------------------------------------------------------------
    # 3. Compute preserved agent IDs before wiping state
    # ------------------------------------------------------------------
    preserved_agent_ids: set[str] = set()

    if get_app_state is not None:
        try:
            app_state = get_app_state()
            for task in (app_state.get("tasks") or {}).values():
                if isinstance(task, dict):
                    is_backgrounded = task.get("is_backgrounded")
                    if is_backgrounded is False:
                        # Foreground task — will be killed
                        continue
                    task_type = task.get("type")
                    if task_type == "local_agent":
                        agent_id = task.get("agent_id")
                        if agent_id:
                            preserved_agent_ids.add(agent_id)
                else:
                    is_backgrounded = getattr(task, "is_backgrounded", None)
                    if is_backgrounded is False:
                        continue
                    task_type = getattr(task, "type", None)
                    if task_type == "local_agent":
                        agent_id = getattr(task, "agent_id", None)
                        if agent_id:
                            preserved_agent_ids.add(agent_id)
        except Exception as exc:
            logger.debug("Could not compute preserved agents: %s", exc)

    # ------------------------------------------------------------------
    # 4. Reset messages
    # ------------------------------------------------------------------
    if set_messages is not None:
        try:
            set_messages(lambda _prev: [])
        except Exception as exc:
            logger.warning("set_messages failed: %s", exc)

    # ------------------------------------------------------------------
    # 5. New conversation ID
    # ------------------------------------------------------------------
    if set_conversation_id is not None:
        try:
            set_conversation_id(str(_uuid_module.uuid4()))
        except Exception as exc:
            logger.debug("set_conversation_id failed: %s", exc)

    # ------------------------------------------------------------------
    # 6. Clear session caches
    # ------------------------------------------------------------------
    try:
        from claude_code.commands.clear.caches import clear_session_caches  # type: ignore[import]
        clear_session_caches(preserved_agent_ids)
    except (ImportError, Exception) as exc:
        logger.debug("clear_session_caches skipped: %s", exc)

    # ------------------------------------------------------------------
    # 7. Reset file state / skill sets / cwd
    # ------------------------------------------------------------------
    try:
        from claude_code.utils.shell import set_cwd  # type: ignore[import]
        from claude_code.bootstrap.state import get_original_cwd  # type: ignore[import]
        set_cwd(get_original_cwd())
    except (ImportError, Exception) as exc:
        logger.debug("set_cwd skipped: %s", exc)

    if read_file_state is not None and hasattr(read_file_state, "clear"):
        try:
            read_file_state.clear()
        except Exception as exc:
            logger.debug("read_file_state.clear failed: %s", exc)

    if discovered_skill_names is not None:
        discovered_skill_names.clear()

    if loaded_nested_memory_paths is not None:
        loaded_nested_memory_paths.clear()

    # ------------------------------------------------------------------
    # 8. Clean app state
    # ------------------------------------------------------------------
    if set_app_state is not None:
        def _clean_app_state(prev: dict) -> dict:
            import time

            tasks_to_kill: list = []
            next_tasks: dict = {}
            prev_tasks = prev.get("tasks") or {}

            for task_id, task in prev_tasks.items():
                if isinstance(task, dict):
                    is_backgrounded = task.get("is_backgrounded")
                else:
                    is_backgrounded = getattr(task, "is_backgrounded", None)

                if is_backgrounded is False:
                    # Kill and drop foreground tasks
                    tasks_to_kill.append((task_id, task))
                else:
                    next_tasks[task_id] = task

            for task_id, task in tasks_to_kill:
                try:
                    if isinstance(task, dict):
                        status = task.get("status")
                        abort_controller = task.get("abort_controller")
                    else:
                        status = getattr(task, "status", None)
                        abort_controller = getattr(task, "abort_controller", None)

                    if status == "running" and abort_controller is not None:
                        if hasattr(abort_controller, "abort"):
                            abort_controller.abort()
                except Exception as exc:
                    logger.warning("Error killing task %s: %s", task_id, exc)

                # Evict disk output fire-and-forget
                try:
                    from claude_code.utils.task.disk_output import evict_task_output  # type: ignore[import]
                    asyncio.ensure_future(evict_task_output(task_id))
                except (ImportError, Exception):
                    pass

            prev_mcp = prev.get("mcp") or {}
            return {
                **prev,
                "tasks": next_tasks,
                "attribution": _empty_attribution(),
                "standalone_agent_context": None,
                "file_history": {
                    "snapshots": [],
                    "tracked_files": set(),
                    "snapshot_sequence": 0,
                },
                "mcp": {
                    "clients": [],
                    "tools": [],
                    "commands": [],
                    "resources": {},
                    "plugin_reconnect_key": prev_mcp.get("plugin_reconnect_key"),
                },
            }

        try:
            set_app_state(_clean_app_state)
        except Exception as exc:
            logger.warning("set_app_state (clean) failed: %s", exc)

    # ------------------------------------------------------------------
    # 9. Clear plan slugs + session metadata
    # ------------------------------------------------------------------
    try:
        from claude_code.utils.plans import clear_all_plan_slugs  # type: ignore[import]
        clear_all_plan_slugs()
    except (ImportError, Exception) as exc:
        logger.debug("clear_all_plan_slugs skipped: %s", exc)

    try:
        from claude_code.utils.session_storage import clear_session_metadata  # type: ignore[import]
        clear_session_metadata()
    except (ImportError, Exception) as exc:
        logger.debug("clear_session_metadata skipped: %s", exc)

    # ------------------------------------------------------------------
    # 10. Regenerate session ID
    # ------------------------------------------------------------------
    try:
        from claude_code.bootstrap.state import regenerate_session_id  # type: ignore[import]
        regenerate_session_id(set_current_as_parent=True)
    except (ImportError, Exception) as exc:
        logger.debug("regenerate_session_id skipped: %s", exc)

    # ------------------------------------------------------------------
    # 11. SessionStart hooks
    # ------------------------------------------------------------------
    hook_messages: list = []
    try:
        from claude_code.utils.session_start import process_session_start_hooks  # type: ignore[import]
        hook_messages = await process_session_start_hooks("clear")
    except (ImportError, Exception) as exc:
        logger.debug("process_session_start_hooks skipped: %s", exc)

    if hook_messages and set_messages is not None:
        try:
            msgs = list(hook_messages)
            set_messages(lambda _prev: msgs)
        except Exception as exc:
            logger.debug("set_messages (hook results) failed: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_attribution() -> dict:
    """Return an empty attribution state (mirrors createEmptyAttributionState)."""
    try:
        from claude_code.utils.commit_attribution import create_empty_attribution_state  # type: ignore[import]
        return create_empty_attribution_state()
    except (ImportError, Exception):
        return {}
