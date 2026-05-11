"""
Teammate Layout Manager.

Manages teammate pane creation, color assignments, and backend delegation
for the swarm view.

原始 TS: utils/swarm/teammateLayoutManager.ts
"""

from typing import Dict, Optional, Tuple

from .backends.types import AgentColorName

# Available agent colors (mirrors agentColorManager.ts)
AGENT_COLORS: Tuple[AgentColorName, ...] = (
    "red",
    "blue",
    "green",
    "yellow",
    "purple",
    "orange",
    "pink",
    "cyan",
)

# Track color assignments for teammates (persisted per session)
_teammate_color_assignments: Dict[str, AgentColorName] = {}
_color_index: int = 0


def assign_teammate_color(teammate_id: str) -> AgentColorName:
    """Assign a unique color to a teammate from the available palette.

    Colors are assigned in round-robin order.

    Args:
        teammate_id: The unique ID of the teammate.

    Returns:
        The assigned color name.
    """
    global _color_index

    existing = _teammate_color_assignments.get(teammate_id)
    if existing:
        return existing

    color: AgentColorName = AGENT_COLORS[_color_index % len(AGENT_COLORS)]
    _teammate_color_assignments[teammate_id] = color
    _color_index += 1

    return color


def get_teammate_color(teammate_id: str) -> Optional[AgentColorName]:
    """Get the assigned color for a teammate, if any.

    Args:
        teammate_id: The unique ID of the teammate.

    Returns:
        The assigned color name, or None if not assigned.
    """
    return _teammate_color_assignments.get(teammate_id)


def clear_teammate_colors() -> None:
    """Clear all teammate color assignments.

    Called during team cleanup to reset state for potential new teams.
    """
    global _color_index
    _teammate_color_assignments.clear()
    _color_index = 0


async def is_inside_tmux() -> bool:
    """Check if we're currently running inside a tmux session."""
    from .backends.detection import is_inside_tmux as check_tmux
    return await check_tmux()


async def create_teammate_pane_in_swarm_view(
    teammate_name: str,
    teammate_color: AgentColorName,
) -> Dict[str, object]:
    """Create a new teammate pane in the swarm view.

    Automatically selects the appropriate backend (tmux or iTerm2) based on environment.

    When running INSIDE tmux:
    - Uses TmuxBackend to split the current window
    - Leader stays on left (30%), teammates on right (70%)

    When running in iTerm2 (not in tmux) with it2 CLI:
    - Uses ITermBackend for native iTerm2 split panes

    When running OUTSIDE tmux/iTerm2:
    - Falls back to TmuxBackend with external claude-swarm session

    Args:
        teammate_name: Display name for the teammate.
        teammate_color: Color for the teammate pane.

    Returns:
        Dict with pane_id and is_first_teammate.
    """
    backend = await _get_backend()
    result = await backend.create_teammate_pane_in_swarm_view(teammate_name, teammate_color)
    return {"paneId": result.pane_id, "isFirstTeammate": result.is_first_teammate}


async def enable_pane_border_status(
    window_target: Optional[str] = None,
    use_swarm_socket: bool = False,
) -> None:
    """Enable pane border status for a window (shows pane titles).

    Args:
        window_target: Target window identifier.
        use_swarm_socket: Whether to use the swarm socket.
    """
    backend = await _get_backend()
    await backend.enable_pane_border_status(window_target, use_swarm_socket)


async def send_command_to_pane(
    pane_id: str,
    command: str,
    use_swarm_socket: bool = False,
) -> None:
    """Send a command to a specific pane.

    Args:
        pane_id: The pane ID to send the command to.
        command: The command string to send.
        use_swarm_socket: Whether to use the swarm socket.
    """
    backend = await _get_backend()
    await backend.send_command_to_pane(pane_id, command, use_swarm_socket)


async def _get_backend():  # type: ignore[return]
    """Get the appropriate backend for the current environment."""
    from .backends.detection import detect_and_get_backend
    result = await detect_and_get_backend()
    return result.backend
