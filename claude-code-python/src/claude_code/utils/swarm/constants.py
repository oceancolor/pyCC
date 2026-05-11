"""
Swarm constants.
原始 TS: utils/swarm/constants.ts
"""

import os

TEAM_LEAD_NAME = "team-lead"
SWARM_SESSION_NAME = "claude-swarm"
SWARM_VIEW_WINDOW_NAME = "swarm-view"
TMUX_COMMAND = "tmux"
HIDDEN_SESSION_NAME = "claude-hidden"


def get_swarm_socket_name() -> str:
    """Gets the socket name for external swarm sessions (when user is not in tmux).
    Uses a separate socket to isolate swarm operations from user's tmux sessions.
    Includes PID to ensure multiple Claude instances don't conflict.
    """
    return f"claude-swarm-{os.getpid()}"


# Environment variable to override the command used to spawn teammate instances.
# If not set, defaults to the current executable path.
TEAMMATE_COMMAND_ENV_VAR = "CLAUDE_CODE_TEAMMATE_COMMAND"

# Environment variable set on spawned teammates to indicate their assigned color.
TEAMMATE_COLOR_ENV_VAR = "CLAUDE_CODE_AGENT_COLOR"

# Environment variable set on spawned teammates to require plan mode before implementation.
PLAN_MODE_REQUIRED_ENV_VAR = "CLAUDE_CODE_PLAN_MODE_REQUIRED"
