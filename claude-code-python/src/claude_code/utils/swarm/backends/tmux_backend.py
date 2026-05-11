"""
TmuxBackend: pane management backend using tmux.

Port of utils/swarm/backends/TmuxBackend.ts
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .detection import get_leader_pane_id, is_inside_tmux as _is_inside_tmux, is_tmux_available
from .registry import register_tmux_backend
from .types import AgentColorName, CreatePaneResult, PaneBackend, PaneId

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_first_pane_used_for_external: bool = False
_cached_leader_window_target: Optional[str] = None

# Sequential lock for pane creation (avoid race conditions when spawning in parallel)
_pane_creation_lock: asyncio.Lock = asyncio.Lock()

# Delay after pane creation to allow shell initialization
_PANE_SHELL_INIT_DELAY_MS: int = 200

# Tmux constants (mirrors constants.ts)
_TMUX_COMMAND = "tmux"
_SWARM_SESSION_NAME = "claude-swarm"
_SWARM_VIEW_WINDOW_NAME = "swarm-view"
_HIDDEN_SESSION_NAME = "claude-hidden"


async def _wait_for_pane_shell_ready() -> None:
    await asyncio.sleep(_PANE_SHELL_INIT_DELAY_MS / 1000.0)


async def _exec_file_no_throw(cmd: str, args: list[str]) -> tuple[str, str, int]:
    """Run a subprocess and return (stdout, stderr, returncode). Never raises."""
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        return (
            stdout_b.decode(errors="replace"),
            stderr_b.decode(errors="replace"),
            proc.returncode or 0,
        )
    except Exception:
        return ("", "", 1)


def _get_tmux_color_name(color: AgentColorName) -> str:
    """Gets the tmux color name for a given agent color."""
    tmux_colors: dict[str, str] = {
        "red": "red",
        "blue": "blue",
        "green": "green",
        "yellow": "yellow",
        "purple": "magenta",
        "orange": "colour208",
        "pink": "colour205",
        "cyan": "cyan",
    }
    return tmux_colors.get(color, "white")


async def _run_tmux_in_user_session(args: list[str]) -> tuple[str, str, int]:
    """
    Runs a tmux command in the user's original tmux session (no socket override).
    Use this for operations that interact with the user's tmux panes.
    """
    return await _exec_file_no_throw(_TMUX_COMMAND, args)


def _get_swarm_socket_name() -> str:
    """Returns the swarm socket name (mirrors getSwarmSocketName from constants.ts)."""
    import os
    return os.environ.get("CLAUDE_SWARM_SOCKET", "claude-swarm-socket")


async def _run_tmux_in_swarm_session(args: list[str]) -> tuple[str, str, int]:
    """
    Runs a tmux command using the swarm socket.
    Use this for operations in the external swarm session.
    """
    socket_args = ["-L", _get_swarm_socket_name()] + args
    return await _exec_file_no_throw(_TMUX_COMMAND, socket_args)


class TmuxBackend(PaneBackend):
    """
    TmuxBackend implements pane management using tmux.

    Supports two modes:
    - Native: Claude is running inside the user's tmux session
    - External: Claude creates a separate tmux session for swarm view
    """

    @property
    def type(self) -> str:
        return "tmux"

    @property
    def display_name(self) -> str:
        return "tmux"

    @property
    def supports_hide_show(self) -> bool:
        return True

    async def is_available(self) -> bool:
        """Checks if tmux is installed and available."""
        return await is_tmux_available()

    async def is_running_inside(self) -> bool:
        """Checks if we're currently running inside a tmux session."""
        return await _is_inside_tmux()

    async def create_teammate_pane_in_swarm_view(
        self,
        name: str,
        color: AgentColorName,
    ) -> CreatePaneResult:
        """Creates a new pane for a teammate in the swarm view."""
        global _first_pane_used_for_external, _cached_leader_window_target

        async with _pane_creation_lock:
            inside_tmux = await _is_inside_tmux()
            is_first = not _first_pane_used_for_external if not inside_tmux else False

            if inside_tmux:
                # Native mode: split the current window
                leader_pane_id = get_leader_pane_id()

                # Get the leader's window target
                if _cached_leader_window_target is None and leader_pane_id:
                    stdout, _, code = await _run_tmux_in_user_session([
                        "display-message",
                        "-p",
                        "-t", leader_pane_id,
                        "#{session_name}:#{window_index}",
                    ])
                    if code == 0:
                        _cached_leader_window_target = stdout.strip()

                window_target = _cached_leader_window_target or ""
                # Split horizontally to create a new pane
                split_args = ["split-window", "-h"]
                if window_target:
                    split_args.extend(["-t", window_target])
                stdout, _, code = await _run_tmux_in_user_session(split_args)
                if code != 0:
                    # Fallback: split vertically
                    split_args[1] = "-v"
                    stdout, _, code = await _run_tmux_in_user_session(split_args)

                # Get the pane ID of the newly created pane
                stdout, _, _ = await _run_tmux_in_user_session([
                    "display-message", "-p", "#{pane_id}"
                ])
                pane_id = stdout.strip()

                await _wait_for_pane_shell_ready()
                return CreatePaneResult(pane_id=pane_id, is_first_teammate=False)
            else:
                # External session mode
                if is_first:
                    _first_pane_used_for_external = True
                    # Create or attach to external swarm session
                    await _run_tmux_in_swarm_session([
                        "new-session", "-d", "-s", _SWARM_SESSION_NAME,
                        "-x", "220", "-y", "50",
                    ])
                    stdout, _, _ = await _run_tmux_in_swarm_session([
                        "display-message", "-p", "-t",
                        f"{_SWARM_SESSION_NAME}:0", "#{pane_id}",
                    ])
                    pane_id = stdout.strip()
                else:
                    # Add another pane to the swarm session
                    await _run_tmux_in_swarm_session([
                        "split-window", "-h", "-t",
                        f"{_SWARM_SESSION_NAME}:{_SWARM_VIEW_WINDOW_NAME}",
                    ])
                    stdout, _, _ = await _run_tmux_in_swarm_session([
                        "display-message", "-p", "#{pane_id}",
                    ])
                    pane_id = stdout.strip()

                await _wait_for_pane_shell_ready()
                return CreatePaneResult(pane_id=pane_id, is_first_teammate=is_first)

    async def send_command_to_pane(
        self,
        pane_id: PaneId,
        command: str,
        use_external_session: bool = False,
    ) -> None:
        """Sends a command to execute in a specific pane."""
        args = ["send-keys", "-t", pane_id, command, "Enter"]
        if use_external_session:
            await _run_tmux_in_swarm_session(args)
        else:
            await _run_tmux_in_user_session(args)

    async def set_pane_border_color(
        self,
        pane_id: PaneId,
        color: AgentColorName,
        use_external_session: bool = False,
    ) -> None:
        """Sets the border color for a pane."""
        tmux_color = _get_tmux_color_name(color)
        args = [
            "select-pane", "-t", pane_id,
            "-P", f"pane-border-style=fg={tmux_color}",
        ]
        if use_external_session:
            await _run_tmux_in_swarm_session(args)
        else:
            await _run_tmux_in_user_session(args)

    async def set_pane_title(
        self,
        pane_id: PaneId,
        name: str,
        color: AgentColorName,
        use_external_session: bool = False,
    ) -> None:
        """Sets the title for a pane."""
        args = ["select-pane", "-t", pane_id, "-T", name]
        if use_external_session:
            await _run_tmux_in_swarm_session(args)
        else:
            await _run_tmux_in_user_session(args)

    async def enable_pane_border_status(
        self,
        window_target: Optional[str] = None,
        use_external_session: bool = False,
    ) -> None:
        """Enables pane border status display."""
        args = ["set-window-option"]
        if window_target:
            args.extend(["-t", window_target])
        args.extend(["pane-border-status", "top"])
        if use_external_session:
            await _run_tmux_in_swarm_session(args)
        else:
            await _run_tmux_in_user_session(args)

    async def rebalance_panes(
        self,
        window_target: str,
        has_leader: bool,
    ) -> None:
        """Rebalances panes using even-horizontal layout."""
        args = [
            "select-layout", "-t", window_target, "even-horizontal"
        ]
        await _run_tmux_in_user_session(args)

    async def kill_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Kills/closes a specific pane."""
        args = ["kill-pane", "-t", pane_id]
        if use_external_session:
            _, _, code = await _run_tmux_in_swarm_session(args)
        else:
            _, _, code = await _run_tmux_in_user_session(args)
        return code == 0

    async def hide_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Hides a pane by breaking it out into a hidden window."""
        args = [
            "break-pane", "-d", "-t", pane_id,
            "-s", f"{_HIDDEN_SESSION_NAME}:",
        ]
        if use_external_session:
            _, _, code = await _run_tmux_in_swarm_session(args)
        else:
            _, _, code = await _run_tmux_in_user_session(args)
        return code == 0

    async def show_pane(
        self,
        pane_id: PaneId,
        target_window_or_pane: str,
        use_external_session: bool = False,
    ) -> bool:
        """Shows a previously hidden pane by joining it back into the main window."""
        args = [
            "join-pane", "-h",
            "-s", pane_id,
            "-t", target_window_or_pane,
        ]
        if use_external_session:
            _, _, code = await _run_tmux_in_swarm_session(args)
        else:
            _, _, code = await _run_tmux_in_user_session(args)
        return code == 0


# Register this backend class with the registry
register_tmux_backend(TmuxBackend)
