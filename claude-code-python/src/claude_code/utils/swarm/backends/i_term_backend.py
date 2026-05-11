"""
ITermBackend: pane management backend using iTerm2's native split panes.

Port of utils/swarm/backends/ITermBackend.ts
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from .detection import IT2_COMMAND, is_in_i_term2, is_it2_cli_available
from .registry import register_i_term_backend
from .types import AgentColorName, CreatePaneResult, PaneBackend, PaneId

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_teammate_session_ids: list[str] = []
_first_pane_used: bool = False
_pane_creation_lock: asyncio.Lock = asyncio.Lock()


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


async def _run_it2(args: list[str]) -> tuple[str, str, int]:
    """Runs an it2 CLI command and returns the result."""
    return await _exec_file_no_throw(IT2_COMMAND, args)


def _parse_split_output(output: str) -> str:
    """
    Parses the session ID from `it2 session split` output.
    Format: "Created new pane: <session-id>"
    """
    import re
    match = re.search(r"Created new pane:\s*(.+)", output)
    if match and match.group(1):
        return match.group(1).strip()
    return ""


def _get_leader_session_id() -> Optional[str]:
    """
    Gets the leader's session ID from ITERM_SESSION_ID env var.
    Format: "wXtYpZ:UUID" — we extract the UUID part after the colon.
    Returns None if not in iTerm2 or env var not set.
    """
    iterm_session_id = os.environ.get("ITERM_SESSION_ID")
    if not iterm_session_id:
        return None
    colon_index = iterm_session_id.find(":")
    if colon_index == -1:
        return None
    return iterm_session_id[colon_index + 1:]


class ITermBackend(PaneBackend):
    """
    ITermBackend implements pane management using iTerm2's native split panes
    via the it2 CLI tool.
    """

    @property
    def type(self) -> str:
        return "iterm2"

    @property
    def display_name(self) -> str:
        return "iTerm2"

    @property
    def supports_hide_show(self) -> bool:
        # iTerm2 doesn't natively support hide/show the way tmux does
        return False

    async def is_available(self) -> bool:
        """Checks if it2 CLI is available and can reach the iTerm2 Python API."""
        return await is_it2_cli_available()

    async def is_running_inside(self) -> bool:
        """Checks if we're running inside iTerm2."""
        return is_in_i_term2()

    async def create_teammate_pane_in_swarm_view(
        self,
        name: str,
        color: AgentColorName,
    ) -> CreatePaneResult:
        """Creates a new pane for a teammate using iTerm2 native split."""
        global _first_pane_used, _teammate_session_ids

        async with _pane_creation_lock:
            is_first = not _first_pane_used
            _first_pane_used = True

            leader_session_id = _get_leader_session_id()

            if leader_session_id and not is_first:
                # Split from the last teammate pane for a more organized layout
                source_session = (
                    _teammate_session_ids[-1]
                    if _teammate_session_ids
                    else leader_session_id
                )
                stdout, _, code = await _run_it2([
                    "session", "split",
                    "-s", source_session,
                    "--vertical",
                ])
            elif leader_session_id:
                # First teammate: split from leader
                stdout, _, code = await _run_it2([
                    "session", "split",
                    "-s", leader_session_id,
                    "--vertical",
                ])
            else:
                # No leader session ID, split the active session
                stdout, _, code = await _run_it2(["session", "split", "--vertical"])

            pane_id = ""
            if code == 0:
                pane_id = _parse_split_output(stdout)
                if pane_id:
                    _teammate_session_ids.append(pane_id)

            if not pane_id:
                # Fallback pane ID
                pane_id = f"iterm2-pane-{len(_teammate_session_ids)}"
                _teammate_session_ids.append(pane_id)

            return CreatePaneResult(pane_id=pane_id, is_first_teammate=is_first)

    async def send_command_to_pane(
        self,
        pane_id: PaneId,
        command: str,
        use_external_session: bool = False,
    ) -> None:
        """Sends a command to execute in a specific iTerm2 pane."""
        await _run_it2(["session", "send", "-s", pane_id, command + "\n"])

    async def set_pane_border_color(
        self,
        pane_id: PaneId,
        color: AgentColorName,
        use_external_session: bool = False,
    ) -> None:
        """iTerm2 doesn't have direct pane border color control via it2 CLI."""
        # No-op: iTerm2 pane styling is handled differently
        logger.debug(
            "[ITermBackend] set_pane_border_color: not supported via it2 CLI"
        )

    async def set_pane_title(
        self,
        pane_id: PaneId,
        name: str,
        color: AgentColorName,
        use_external_session: bool = False,
    ) -> None:
        """Sets the title for an iTerm2 pane."""
        await _run_it2(["session", "title", "-s", pane_id, name])

    async def enable_pane_border_status(
        self,
        window_target: Optional[str] = None,
        use_external_session: bool = False,
    ) -> None:
        """Not applicable for iTerm2 — no-op."""
        pass

    async def rebalance_panes(
        self,
        window_target: str,
        has_leader: bool,
    ) -> None:
        """Not applicable for iTerm2 native panes — no-op."""
        pass

    async def kill_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """Kills/closes a specific iTerm2 pane."""
        _, _, code = await _run_it2(["session", "close", "-s", pane_id])
        if code == 0 and pane_id in _teammate_session_ids:
            _teammate_session_ids.remove(pane_id)
        return code == 0

    async def hide_pane(
        self,
        pane_id: PaneId,
        use_external_session: bool = False,
    ) -> bool:
        """iTerm2 doesn't support hide/show — returns False."""
        return False

    async def show_pane(
        self,
        pane_id: PaneId,
        target_window_or_pane: str,
        use_external_session: bool = False,
    ) -> bool:
        """iTerm2 doesn't support hide/show — returns False."""
        return False


# Register this backend class with the registry
register_i_term_backend(ITermBackend)
