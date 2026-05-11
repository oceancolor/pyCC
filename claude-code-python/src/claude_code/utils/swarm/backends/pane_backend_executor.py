"""
PaneBackendExecutor: adapts a PaneBackend to the TeammateExecutor interface.

Port of utils/swarm/backends/PaneBackendExecutor.ts
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from .types import (
    BackendType,
    PaneBackend,
    TeammateExecutor,
    TeammateMessage,
    TeammateSpawnConfig,
    TeammateSpawnResult,
)

logger = logging.getLogger(__name__)


def _format_agent_id(name: str, team_name: str) -> str:
    """Format agent ID as 'name@teamName'."""
    return f"{name}@{team_name}"


class PaneBackendExecutor(TeammateExecutor):
    """
    PaneBackendExecutor adapts a PaneBackend to the TeammateExecutor interface.

    This allows pane-based backends (tmux, iTerm2) to be used through the same
    TeammateExecutor abstraction as InProcessBackend.

    The adapter handles:
    - spawn(): Creates a pane and sends the Claude CLI command to it
    - send_message(): Writes to the teammate's file-based mailbox
    - terminate(): Sends a shutdown request via mailbox
    - kill(): Kills the pane via the backend
    - is_active(): Checks if the pane is still running
    """

    def __init__(self, backend: PaneBackend) -> None:
        self._backend = backend
        self._context: Optional[Any] = None
        # Map agentId -> {"pane_id": str, "inside_tmux": bool}
        self._spawned_teammates: dict[str, dict[str, Any]] = {}

    @property
    def type(self) -> BackendType:
        return self._backend.type  # type: ignore[return-value]

    def set_context(self, context: Any) -> None:
        """
        Sets the ToolUseContext for this executor.
        Must be called before spawn() to provide access to AppState and permissions.
        """
        self._context = context

    async def is_available(self) -> bool:
        """Checks if the underlying pane backend is available."""
        return await self._backend.is_available()

    async def spawn(self, config: TeammateSpawnConfig) -> TeammateSpawnResult:
        """
        Spawns a teammate in a new pane.

        Creates a pane via the backend, builds the CLI command with teammate
        identity flags, and sends it to the pane.
        """
        agent_id = _format_agent_id(config.name, config.team_name)
        logger.debug("[PaneBackendExecutor] spawn() called for %s", agent_id)

        try:
            # Assign a color for this teammate
            color = config.color or "blue"

            # Create the pane
            pane_result = await self._backend.create_teammate_pane_in_swarm_view(
                config.name, color
            )
            pane_id = pane_result.pane_id

            # Enable border status on first teammate
            if pane_result.is_first_teammate:
                try:
                    await self._backend.enable_pane_border_status()
                except Exception:
                    pass

            # Set pane title and color
            try:
                await self._backend.set_pane_title(pane_id, config.name, color)
                await self._backend.set_pane_border_color(pane_id, color)
            except Exception:
                pass

            # Build the CLI command for the teammate
            command = _build_teammate_command(config)

            # Send the command to the pane
            from .detection import is_inside_tmux_sync

            inside_tmux = is_inside_tmux_sync()
            await self._backend.send_command_to_pane(
                pane_id, command, use_external_session=not inside_tmux
            )

            # Track this teammate
            self._spawned_teammates[agent_id] = {
                "pane_id": pane_id,
                "inside_tmux": inside_tmux,
            }

            # Rebalance panes if we have more than one
            if len(self._spawned_teammates) > 1:
                try:
                    await self._backend.rebalance_panes("", bool(inside_tmux))
                except Exception:
                    pass

            logger.debug(
                "[PaneBackendExecutor] Spawned %s in pane %s", agent_id, pane_id
            )
            return TeammateSpawnResult(
                success=True,
                agent_id=agent_id,
                pane_id=pane_id,
            )
        except Exception as e:
            logger.debug(
                "[PaneBackendExecutor] spawn() failed for %s: %s", agent_id, e
            )
            return TeammateSpawnResult(
                success=False,
                agent_id=agent_id,
                error=str(e),
            )

    async def send_message(
        self, agent_id: str, message: TeammateMessage
    ) -> None:
        """Sends a message to a teammate via file-based mailbox."""
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
                "[PaneBackendExecutor] send_message() failed for %s: %s", agent_id, e
            )

    async def terminate(
        self, agent_id: str, reason: Optional[str] = None
    ) -> bool:
        """Sends a graceful shutdown request to a teammate."""
        try:
            from ...utils.teammate_mailbox import (  # type: ignore[import]
                create_shutdown_request_message,
                write_to_mailbox,
            )

            shutdown_msg = create_shutdown_request_message(reason)
            await write_to_mailbox(agent_id, shutdown_msg)
            return True
        except Exception as e:
            logger.debug(
                "[PaneBackendExecutor] terminate() failed for %s: %s", agent_id, e
            )
            return False

    async def kill(self, agent_id: str) -> bool:
        """Force kills a teammate by killing the pane."""
        teammate = self._spawned_teammates.get(agent_id)
        if not teammate:
            logger.debug(
                "[PaneBackendExecutor] kill(): no pane found for %s", agent_id
            )
            return False

        pane_id = teammate["pane_id"]
        inside_tmux = teammate["inside_tmux"]

        success = await self._backend.kill_pane(
            pane_id, use_external_session=not inside_tmux
        )
        if success:
            del self._spawned_teammates[agent_id]
        return success

    async def is_active(self, agent_id: str) -> bool:
        """Checks if a teammate pane is still running."""
        teammate = self._spawned_teammates.get(agent_id)
        if not teammate:
            return False
        # For pane-based backends, we assume the pane is active if we have a record of it.
        # A more robust check would query the backend, but that requires additional API.
        return True


def _build_teammate_command(config: TeammateSpawnConfig) -> str:
    """Build the CLI command string to launch a teammate process."""
    parts = ["claude"]

    parts.extend(["--teammate-name", config.name])
    parts.extend(["--team-name", config.team_name])
    parts.extend(["--parent-session-id", config.parent_session_id])

    if config.model:
        parts.extend(["--model", config.model])
    if config.system_prompt:
        parts.extend(["--system-prompt", _shell_quote(config.system_prompt)])
    if config.system_prompt_mode:
        parts.extend(["--system-prompt-mode", config.system_prompt_mode])
    if config.worktree_path:
        parts.extend(["--worktree", config.worktree_path])
    if config.color:
        parts.extend(["--color", config.color])
    if config.plan_mode_required:
        parts.append("--plan-mode-required")
    if config.permissions:
        for perm in config.permissions:
            parts.extend(["--allow-tool", perm])
    if config.allow_permission_prompts:
        parts.append("--allow-permission-prompts")

    if config.cwd:
        # Change directory first
        cmd_str = f"cd {_shell_quote(config.cwd)} && "
    else:
        cmd_str = ""

    prompt = _shell_quote(config.prompt)
    cmd_str += f"{' '.join(parts)} {prompt}"
    return cmd_str


def _shell_quote(s: str) -> str:
    """Simple shell quoting — wraps string in single quotes, escaping embedded single quotes."""
    return "'" + s.replace("'", "'\\''") + "'"


def create_pane_backend_executor(backend: PaneBackend) -> PaneBackendExecutor:
    """Factory function to create a PaneBackendExecutor."""
    return PaneBackendExecutor(backend)
