"""
InProcessBackend: runs teammates in the same Python process.

Port of utils/swarm/backends/InProcessBackend.ts
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .types import (
    BackendType,
    TeammateExecutor,
    TeammateMessage,
    TeammateSpawnConfig,
    TeammateSpawnResult,
)

logger = logging.getLogger(__name__)


class InProcessBackend(TeammateExecutor):
    """
    InProcessBackend implements TeammateExecutor for in-process teammates.

    Unlike pane-based backends (tmux/iTerm2), in-process teammates run in the
    same Python process with isolated context. They:
    - Share resources (API client, MCP connections) with the leader
    - Communicate via file-based mailbox (same as pane-based teammates)
    - Are terminated via cancellation tokens / asyncio.Task.cancel()

    IMPORTANT: Before spawning, call set_context() to provide the ToolUseContext
    needed for AppState access.
    """

    def __init__(self) -> None:
        self._context: Optional[Any] = None

    @property
    def type(self) -> BackendType:
        return "in-process"

    def set_context(self, context: Any) -> None:
        """
        Sets the ToolUseContext for this backend.
        Called by TeammateTool before spawning to provide AppState access.
        """
        self._context = context

    async def is_available(self) -> bool:
        """In-process backend is always available (no external dependencies)."""
        return True

    async def spawn(self, config: TeammateSpawnConfig) -> TeammateSpawnResult:
        """
        Spawns an in-process teammate.

        Uses spawn_in_process_teammate() to:
        1. Create TeammateContext
        2. Create independent asyncio Task (not linked to parent)
        3. Register teammate in AppState.tasks
        4. Start agent execution
        5. Return spawn result with agent_id, task_id
        """
        agent_id = f"{config.name}@{config.team_name}"

        if self._context is None:
            logger.debug(
                "[InProcessBackend] spawn() called without context for %s", config.name
            )
            return TeammateSpawnResult(
                success=False,
                agent_id=agent_id,
                error="InProcessBackend not initialized. Call set_context() before spawn().",
            )

        logger.debug("[InProcessBackend] spawn() called for %s", config.name)

        try:
            from ...spawn_in_process import spawn_in_process_teammate  # type: ignore[import]

            result = await spawn_in_process_teammate(
                {
                    "name": config.name,
                    "team_name": config.team_name,
                    "prompt": config.prompt,
                    "color": config.color,
                    "plan_mode_required": config.plan_mode_required or False,
                },
                self._context,
            )

            if result.get("success") and result.get("task_id"):
                from ...in_process_runner import start_in_process_teammate  # type: ignore[import]

                asyncio.ensure_future(
                    start_in_process_teammate(result["task_id"], self._context)
                )

            return TeammateSpawnResult(
                success=result.get("success", False),
                agent_id=result.get("agent_id", agent_id),
                task_id=result.get("task_id"),
                error=result.get("error"),
            )
        except Exception as e:
            logger.debug("[InProcessBackend] spawn() failed: %s", e)
            return TeammateSpawnResult(
                success=False,
                agent_id=agent_id,
                error=str(e),
            )

    async def send_message(
        self, agent_id: str, message: TeammateMessage
    ) -> None:
        """Sends a message to an in-process teammate via file-based mailbox."""
        try:
            from ...utils.teammate_mailbox import write_to_mailbox  # type: ignore[import]

            await write_to_mailbox(
                agent_id,
                {
                    "text": message.text,
                    "from": message.from_agent,
                    "color": message.color,
                    "timestamp": message.timestamp,
                    "summary": message.summary,
                },
            )
        except Exception as e:
            logger.debug(
                "[InProcessBackend] send_message() failed for %s: %s", agent_id, e
            )

    async def terminate(
        self, agent_id: str, reason: Optional[str] = None
    ) -> bool:
        """Sends a graceful shutdown request to an in-process teammate."""
        try:
            from ...tasks.in_process_teammate_task import (  # type: ignore[import]
                request_teammate_shutdown,
            )

            return await request_teammate_shutdown(agent_id, reason)
        except Exception as e:
            logger.debug(
                "[InProcessBackend] terminate() failed for %s: %s", agent_id, e
            )
            return False

    async def kill(self, agent_id: str) -> bool:
        """Force kills an in-process teammate by cancelling its task."""
        try:
            from ...spawn_in_process import kill_in_process_teammate  # type: ignore[import]

            return await kill_in_process_teammate(agent_id)
        except Exception as e:
            logger.debug(
                "[InProcessBackend] kill() failed for %s: %s", agent_id, e
            )
            return False

    async def is_active(self, agent_id: str) -> bool:
        """Checks if an in-process teammate task is still running."""
        try:
            from ...tasks.in_process_teammate_task import (  # type: ignore[import]
                find_teammate_task_by_agent_id,
            )

            task = find_teammate_task_by_agent_id(agent_id)
            if task is None:
                return False
            return not task.done()
        except Exception:
            return False


# Avoid circular import: import asyncio at bottom
import asyncio  # noqa: E402


def create_in_process_backend() -> InProcessBackend:
    """Factory function to create an InProcessBackend instance."""
    return InProcessBackend()
