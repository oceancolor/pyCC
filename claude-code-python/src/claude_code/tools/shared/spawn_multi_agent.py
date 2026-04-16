"""
Spawn multi-agent module. Ported from tools/shared/spawnMultiAgent.ts

Shared spawn module for teammate creation.
Supports three backends:
  - tmux split-pane (default when inside tmux session)
  - tmux separate window (legacy behaviour)
  - in-process (same Python process via asyncio tasks)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants  (mirror swarm/constants.ts)
# ---------------------------------------------------------------------------

SWARM_SESSION_NAME = "claude-swarm"
TEAM_LEAD_NAME = "team-lead"
TEAMMATE_COMMAND_ENV_VAR = "CLAUDE_CODE_TEAMMATE_COMMAND"
TMUX_COMMAND = "tmux"

# ---------------------------------------------------------------------------
# BackendType enum
# ---------------------------------------------------------------------------


class BackendType(str, Enum):
    """Available backends for spawning teammate agents."""

    TMUX = "tmux"
    ITERM2 = "iterm2"
    IN_PROCESS = "in-process"


def is_pane_backend(backend_type: BackendType) -> bool:
    """Return True if the backend manages terminal panes (tmux or iterm2)."""
    return backend_type in (BackendType.TMUX, BackendType.ITERM2)


# ---------------------------------------------------------------------------
# Output / Config types
# ---------------------------------------------------------------------------


@dataclass
class SpawnOutput:
    """Result returned by spawn_teammate / spawn_multi_agent."""

    teammate_id: str
    agent_id: str
    name: str
    tmux_session_name: str
    tmux_window_name: str
    tmux_pane_id: str
    agent_type: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    team_name: Optional[str] = None
    is_splitpane: Optional[bool] = None
    plan_mode_required: Optional[bool] = None


@dataclass
class SpawnTeammateConfig:
    """Public configuration for spawning a teammate."""

    name: str
    prompt: str
    team_name: Optional[str] = None
    cwd: Optional[str] = None
    use_splitpane: Optional[bool] = None
    plan_mode_required: Optional[bool] = None
    model: Optional[str] = None
    agent_type: Optional[str] = None
    description: Optional[str] = None
    invoking_request_id: Optional[str] = None


# Internal alias
SpawnInput = SpawnTeammateConfig


# ---------------------------------------------------------------------------
# Tmux helper functions
# ---------------------------------------------------------------------------


async def _run_tmux(*args: str) -> subprocess.CompletedProcess:
    """Run a tmux sub-command, returning a CompletedProcess-like result."""
    proc = await asyncio.create_subprocess_exec(
        TMUX_COMMAND,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return _TmuxResult(
        returncode=proc.returncode or 0,
        stdout=stdout.decode().strip(),
        stderr=stderr.decode().strip(),
    )


class _TmuxResult:
    """Lightweight holder for tmux subprocess result."""

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


async def has_session(session_name: str) -> bool:
    """Check whether a tmux session exists."""
    result = await _run_tmux("has-session", "-t", session_name)
    return result.returncode == 0


async def ensure_session(session_name: str) -> None:
    """Create a new tmux session if it does not already exist."""
    if not await has_session(session_name):
        result = await _run_tmux("new-session", "-d", "-s", session_name)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create tmux session '{session_name}': "
                f"{result.stderr or 'Unknown error'}"
            )


async def is_inside_tmux() -> bool:
    """Return True when the current process is running inside a tmux session."""
    return bool(os.environ.get("TMUX"))


async def is_tmux_available() -> bool:
    """Return True when the tmux executable is on $PATH."""
    return shutil.which(TMUX_COMMAND) is not None


def get_teammate_command() -> str:
    """
    Return the executable that should be used to spawn a teammate process.
    Respects the TEAMMATE_COMMAND_ENV_VAR override; otherwise uses sys.executable.
    """
    override = os.environ.get(TEAMMATE_COMMAND_ENV_VAR)
    if override:
        return override
    return sys.executable


def _shell_quote(value: str) -> str:
    """Minimally shell-quote a single value (single-quote wrapping)."""
    escaped = value.replace("'", "'\\''")
    return f"'{escaped}'"


def get_teammate_layout(count: int) -> str:
    """
    Return the tmux layout string appropriate for *count* teammate panes.

    Mirrors the logic in teammateLayoutManager.ts:
      1  pane  → main-vertical (leader left, one right)
      2  panes → main-vertical (leader left, two stacked right)
      3+ panes → tiled
    """
    if count <= 1:
        return "main-vertical"
    if count == 2:
        return "main-vertical"
    return "tiled"


def assign_teammate_color(teammate_id: str) -> str:
    """Assign a deterministic terminal colour for a teammate from their ID."""
    _COLORS = [
        "cyan",
        "magenta",
        "yellow",
        "green",
        "blue",
        "red",
        "white",
        "bright-cyan",
        "bright-magenta",
        "bright-yellow",
    ]
    idx = abs(hash(teammate_id)) % len(_COLORS)
    return _COLORS[idx]


async def create_teammate_pane_in_swarm_view(
    name: str,
    color: str,
) -> Tuple[str, bool]:
    """
    Create a pane for a new teammate.

    - When inside tmux: split-window in the current window.
    - Otherwise: create the SWARM_SESSION_NAME session and add a window.

    Returns (pane_id, is_first_teammate).
    """
    inside = await is_inside_tmux()

    if inside:
        # Split the current window horizontally
        result = await _run_tmux(
            "split-window",
            "-h",
            "-P",
            "-F",
            "#{pane_id}",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create tmux split-pane: {result.stderr}"
            )
        pane_id = result.stdout.strip()

        # Check whether this is the first teammate (only 2 panes = leader + first)
        list_result = await _run_tmux("list-panes", "-F", "#{pane_id}")
        is_first = len(list_result.stdout.strip().splitlines()) == 2
        return pane_id, is_first
    else:
        await ensure_session(SWARM_SESSION_NAME)
        window_name = f"teammate-{name}"
        result = await _run_tmux(
            "new-window",
            "-t",
            SWARM_SESSION_NAME,
            "-n",
            window_name,
            "-P",
            "-F",
            "#{pane_id}",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create tmux window: {result.stderr}"
            )
        pane_id = result.stdout.strip()
        return pane_id, False


async def enable_pane_border_status() -> None:
    """Enable pane border status bars in the current tmux window."""
    await _run_tmux("set-window-option", "pane-border-status", "top")


async def send_command_to_pane(
    pane_id: str,
    command: str,
    use_swarm_socket: bool = False,
) -> None:
    """Send *command* to a tmux pane and press Enter."""
    target = pane_id
    args = ["send-keys", "-t", target, command, "Enter"]
    result = await _run_tmux(*args)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to send command to tmux pane {pane_id}: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# Team-file helpers (lightweight stubs — real impl in swarm/teamHelpers.py)
# ---------------------------------------------------------------------------


def sanitize_agent_name(name: str) -> str:
    """Remove characters that would break agentName@teamName format."""
    import re
    return re.sub(r"[^a-zA-Z0-9_\-]", "-", name)


def sanitize_name(name: str) -> str:
    """Lowercase + alphanumeric-only name for window titles."""
    import re
    return re.sub(r"[^a-z0-9\-]", "-", name.lower())


def format_agent_id(agent_name: str, team_name: str) -> str:
    """Return the canonical agentName@teamName identifier."""
    return f"{agent_name}@{team_name}"


async def read_team_file(team_name: str) -> Optional[Dict[str, Any]]:
    """
    Read the team JSON file for *team_name*.
    Returns None if the team does not exist yet.
    """
    import json

    team_dir = os.path.join(os.path.expanduser("~"), ".claude", "teams")
    path = os.path.join(team_dir, f"{team_name}.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


async def write_team_file(team_name: str, data: Dict[str, Any]) -> None:
    """Persist *data* as the team JSON file for *team_name*."""
    import json

    team_dir = os.path.join(os.path.expanduser("~"), ".claude", "teams")
    os.makedirs(team_dir, exist_ok=True)
    path = os.path.join(team_dir, f"{team_name}.json")
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


async def write_to_mailbox(
    recipient_name: str,
    message: Dict[str, Any],
    team_name: str,
) -> None:
    """Append a message to a teammate's mailbox file."""
    import json

    mailbox_dir = os.path.join(
        os.path.expanduser("~"), ".claude", "mailboxes", team_name
    )
    os.makedirs(mailbox_dir, exist_ok=True)
    path = os.path.join(mailbox_dir, f"{recipient_name}.jsonl")
    with open(path, "a") as fh:
        fh.write(json.dumps(message) + "\n")


# ---------------------------------------------------------------------------
# Unique name generation
# ---------------------------------------------------------------------------


async def generate_unique_teammate_name(
    base_name: str,
    team_name: Optional[str],
) -> str:
    """
    Generate a unique teammate name within a team.
    If the name already exists, append a numeric suffix (e.g. tester-2).
    """
    if not team_name:
        return base_name

    team_file = await read_team_file(team_name)
    if not team_file:
        return base_name

    existing_names = {m["name"].lower() for m in team_file.get("members", [])}

    if base_name.lower() not in existing_names:
        return base_name

    suffix = 2
    while f"{base_name}-{suffix}".lower() in existing_names:
        suffix += 1

    return f"{base_name}-{suffix}"


# ---------------------------------------------------------------------------
# In-process spawn
# ---------------------------------------------------------------------------


# Registry of running in-process teammates keyed by teammate_id
_in_process_tasks: Dict[str, asyncio.Task] = {}


async def start_in_process_teammate(config: Dict[str, Any]) -> None:
    """
    Start an in-process teammate agent as an asyncio Task.
    The task is registered in _in_process_tasks for lifecycle management.
    Config keys: identity, task_id, prompt, model, teammate_context, tool_use_context
    """
    teammate_id = config.get("identity", {}).get("agent_id", "unknown")
    logger.debug("[start_in_process_teammate] Starting agent %s", teammate_id)

    async def _run() -> None:
        try:
            prompt = config.get("prompt", "")
            logger.debug(
                "[start_in_process_teammate] Agent %s running with prompt: %s",
                teammate_id,
                prompt[:80],
            )
            # In a full implementation this would invoke the main agent loop.
            # Here we yield to let other coroutines run.
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            logger.debug(
                "[start_in_process_teammate] Agent %s cancelled", teammate_id
            )
        except Exception as exc:
            logger.exception(
                "[start_in_process_teammate] Agent %s error: %s", teammate_id, exc
            )

    task = asyncio.ensure_future(_run())
    _in_process_tasks[teammate_id] = task


def get_active_in_process_teammates() -> List[str]:
    """Return IDs of currently running in-process teammate tasks."""
    return [
        tid
        for tid, task in _in_process_tasks.items()
        if not task.done()
    ]


# ---------------------------------------------------------------------------
# Spawn handlers
# ---------------------------------------------------------------------------


async def _handle_spawn_split_pane(
    input: SpawnInput,
    app_state: Optional[Dict[str, Any]] = None,
) -> SpawnOutput:
    """
    Spawn a teammate using split-pane view.
    Inside tmux: splits current window.
    Outside tmux: creates claude-swarm session with tiled layout.
    """
    app_state = app_state or {}
    name = input.name
    prompt = input.prompt
    agent_type = input.agent_type
    cwd = input.cwd or os.getcwd()
    plan_mode_required = input.plan_mode_required
    model = input.model

    if not name or not prompt:
        raise ValueError("name and prompt are required for spawn operation")

    team_name = input.team_name or (app_state.get("team_context") or {}).get(
        "team_name"
    )
    if not team_name:
        raise ValueError(
            "team_name is required for spawn operation. "
            "Either provide team_name in input or call spawn_team first."
        )

    unique_name = await generate_unique_teammate_name(name, team_name)
    sanitized_name = sanitize_agent_name(unique_name)
    teammate_id = format_agent_id(sanitized_name, team_name)

    inside_tmux = await is_inside_tmux()
    teammate_color = assign_teammate_color(teammate_id)

    pane_id, is_first_teammate = await create_teammate_pane_in_swarm_view(
        sanitized_name, teammate_color
    )

    if is_first_teammate and inside_tmux:
        await enable_pane_border_status()

    binary_path = get_teammate_command()
    teammate_args = _build_teammate_args(
        teammate_id, sanitized_name, team_name, teammate_color,
        plan_mode_required, agent_type,
    )
    inherited_flags = _build_inherited_flags(plan_mode_required, model)
    env_str = _build_inherited_env_vars()

    spawn_command = (
        f"cd {_shell_quote(cwd)} && "
        f"env {env_str} {_shell_quote(binary_path)} "
        f"{teammate_args}{inherited_flags}"
    )

    await send_command_to_pane(pane_id, spawn_command, not inside_tmux)

    session_name = "current" if inside_tmux else SWARM_SESSION_NAME
    window_name = "current" if inside_tmux else "swarm-view"

    await _register_in_team_file(
        team_name, teammate_id, sanitized_name, agent_type, model,
        prompt, teammate_color, plan_mode_required, pane_id, cwd,
        backend_type=BackendType.TMUX,
    )

    await write_to_mailbox(
        sanitized_name,
        {
            "from": TEAM_LEAD_NAME,
            "text": prompt,
            "timestamp": _iso_now(),
        },
        team_name,
    )

    return SpawnOutput(
        teammate_id=teammate_id,
        agent_id=teammate_id,
        agent_type=agent_type,
        model=model,
        name=sanitized_name,
        color=teammate_color,
        tmux_session_name=session_name,
        tmux_window_name=window_name,
        tmux_pane_id=pane_id,
        team_name=team_name,
        is_splitpane=True,
        plan_mode_required=plan_mode_required,
    )


async def _handle_spawn_separate_window(
    input: SpawnInput,
    app_state: Optional[Dict[str, Any]] = None,
) -> SpawnOutput:
    """
    Handle spawn operation using separate tmux windows (legacy behavior).
    Creates each teammate in its own tmux window within the swarm session.
    """
    app_state = app_state or {}
    name = input.name
    prompt = input.prompt
    agent_type = input.agent_type
    cwd = input.cwd or os.getcwd()
    plan_mode_required = input.plan_mode_required
    model = input.model

    if not name or not prompt:
        raise ValueError("name and prompt are required for spawn operation")

    team_name = input.team_name or (app_state.get("team_context") or {}).get(
        "team_name"
    )
    if not team_name:
        raise ValueError(
            "team_name is required for spawn operation. "
            "Either provide team_name in input or call spawn_team first."
        )

    unique_name = await generate_unique_teammate_name(name, team_name)
    sanitized_name = sanitize_agent_name(unique_name)
    teammate_id = format_agent_id(sanitized_name, team_name)
    window_name = f"teammate-{sanitize_name(sanitized_name)}"

    await ensure_session(SWARM_SESSION_NAME)

    teammate_color = assign_teammate_color(teammate_id)

    create_result = await _run_tmux(
        "new-window",
        "-t",
        SWARM_SESSION_NAME,
        "-n",
        window_name,
        "-P",
        "-F",
        "#{pane_id}",
    )
    if create_result.returncode != 0:
        raise RuntimeError(
            f"Failed to create tmux window: {create_result.stderr}"
        )

    pane_id = create_result.stdout.strip()

    binary_path = get_teammate_command()
    teammate_args = _build_teammate_args(
        teammate_id, sanitized_name, team_name, teammate_color,
        plan_mode_required, agent_type,
    )
    inherited_flags = _build_inherited_flags(plan_mode_required, model)
    env_str = _build_inherited_env_vars()

    spawn_command = (
        f"cd {_shell_quote(cwd)} && "
        f"env {env_str} {_shell_quote(binary_path)} "
        f"{teammate_args}{inherited_flags}"
    )

    send_keys_result = await _run_tmux(
        "send-keys",
        "-t",
        f"{SWARM_SESSION_NAME}:{window_name}",
        spawn_command,
        "Enter",
    )
    if send_keys_result.returncode != 0:
        raise RuntimeError(
            f"Failed to send command to tmux window: {send_keys_result.stderr}"
        )

    await _register_in_team_file(
        team_name, teammate_id, sanitized_name, agent_type, model,
        prompt, teammate_color, plan_mode_required, pane_id, cwd,
        backend_type=BackendType.TMUX,
    )

    await write_to_mailbox(
        sanitized_name,
        {
            "from": TEAM_LEAD_NAME,
            "text": prompt,
            "timestamp": _iso_now(),
        },
        team_name,
    )

    return SpawnOutput(
        teammate_id=teammate_id,
        agent_id=teammate_id,
        agent_type=agent_type,
        model=model,
        name=sanitized_name,
        color=teammate_color,
        tmux_session_name=SWARM_SESSION_NAME,
        tmux_window_name=window_name,
        tmux_pane_id=pane_id,
        team_name=team_name,
        is_splitpane=False,
        plan_mode_required=plan_mode_required,
    )


async def _handle_spawn_in_process(
    input: SpawnInput,
    app_state: Optional[Dict[str, Any]] = None,
) -> SpawnOutput:
    """
    Spawn an in-process teammate running as an asyncio Task in the same process.
    """
    app_state = app_state or {}
    name = input.name
    prompt = input.prompt
    agent_type = input.agent_type
    plan_mode_required = input.plan_mode_required
    model = input.model

    if not name or not prompt:
        raise ValueError("name and prompt are required for spawn operation")

    team_name = input.team_name or (app_state.get("team_context") or {}).get(
        "team_name"
    )
    if not team_name:
        raise ValueError(
            "team_name is required for spawn operation. "
            "Either provide team_name in input or call spawn_team first."
        )

    unique_name = await generate_unique_teammate_name(name, team_name)
    sanitized_name = sanitize_agent_name(unique_name)
    teammate_id = format_agent_id(sanitized_name, team_name)
    teammate_color = assign_teammate_color(teammate_id)

    await start_in_process_teammate(
        {
            "identity": {
                "agent_id": teammate_id,
                "agent_name": sanitized_name,
                "team_name": team_name,
                "color": teammate_color,
                "plan_mode_required": plan_mode_required or False,
            },
            "prompt": prompt,
            "model": model,
        }
    )

    await _register_in_team_file(
        team_name, teammate_id, sanitized_name, agent_type, model,
        prompt, teammate_color, plan_mode_required,
        pane_id="in-process", cwd=os.getcwd(),
        backend_type=BackendType.IN_PROCESS,
    )

    # Do NOT write to mailbox for in-process teammates —
    # they receive the prompt directly via start_in_process_teammate().

    return SpawnOutput(
        teammate_id=teammate_id,
        agent_id=teammate_id,
        agent_type=agent_type,
        model=model,
        name=sanitized_name,
        color=teammate_color,
        tmux_session_name="in-process",
        tmux_window_name="in-process",
        tmux_pane_id="in-process",
        team_name=team_name,
        is_splitpane=False,
        plan_mode_required=plan_mode_required,
    )


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------


async def spawn_multi_agent(
    config: SpawnTeammateConfig,
    app_state: Optional[Dict[str, Any]] = None,
    *,
    backend: Optional[BackendType] = None,
    use_splitpane: bool = True,
) -> SpawnOutput:
    """
    Spawn a new agent teammate.

    Routing logic (mirrors handleSpawn in TS):
      1. If backend is explicitly IN_PROCESS → in-process.
      2. Otherwise attempt split-pane or separate-window depending on
         use_splitpane (True by default).
      3. Fall back to in-process if no tmux backend is available.

    Args:
        config: Teammate configuration.
        app_state: Current application state dict (for team context inheritance).
        backend: Override the backend type.
        use_splitpane: When using tmux, prefer split-pane over separate window.

    Returns:
        SpawnOutput with details about the spawned teammate.
    """
    if backend == BackendType.IN_PROCESS:
        return await _handle_spawn_in_process(config, app_state)

    # Try tmux / pane-based spawn; fall back to in-process if unavailable
    if not await is_tmux_available():
        logger.debug(
            "[spawn_multi_agent] tmux not available, falling back to in-process"
        )
        return await _handle_spawn_in_process(config, app_state)

    try:
        eff_use_splitpane = (
            config.use_splitpane
            if config.use_splitpane is not None
            else use_splitpane
        )
        if eff_use_splitpane:
            return await _handle_spawn_split_pane(config, app_state)
        return await _handle_spawn_separate_window(config, app_state)
    except Exception as exc:
        logger.warning(
            "[spawn_multi_agent] Pane-based spawn failed, falling back to "
            "in-process: %s",
            exc,
        )
        return await _handle_spawn_in_process(config, app_state)


# spawn_teammate is the canonical entry-point (matches TS export name)
async def spawn_teammate(
    config: SpawnTeammateConfig,
    app_state: Optional[Dict[str, Any]] = None,
) -> SpawnOutput:
    """Main entry point for spawning a teammate. Wraps spawn_multi_agent."""
    return await spawn_multi_agent(config, app_state)


# resolve_teammate_model is exported for testing (mirrors TS export)
def resolve_teammate_model(
    input_model: Optional[str],
    leader_model: Optional[str],
    default_model: str = "claude-opus-4-5",
) -> str:
    """
    Resolve the effective teammate model.
    'inherit' → substitute leader's model.
    None → use configured default.
    """
    if input_model == "inherit":
        return leader_model or default_model
    return input_model or default_model


# ---------------------------------------------------------------------------
# create_tmux_session (convenience wrapper used by external callers)
# ---------------------------------------------------------------------------


async def create_tmux_session(
    session_name: str = SWARM_SESSION_NAME,
    *,
    detached: bool = True,
) -> None:
    """Create a new tmux session. Raises if creation fails."""
    await ensure_session(session_name)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_teammate_args(
    teammate_id: str,
    sanitized_name: str,
    team_name: str,
    color: str,
    plan_mode_required: Optional[bool],
    agent_type: Optional[str],
) -> str:
    parts = [
        f"--agent-id {_shell_quote(teammate_id)}",
        f"--agent-name {_shell_quote(sanitized_name)}",
        f"--team-name {_shell_quote(team_name)}",
        f"--agent-color {_shell_quote(color)}",
    ]
    if plan_mode_required:
        parts.append("--plan-mode-required")
    if agent_type:
        parts.append(f"--agent-type {_shell_quote(agent_type)}")
    return " ".join(parts)


def _build_inherited_flags(
    plan_mode_required: Optional[bool],
    model: Optional[str],
) -> str:
    """Build CLI flags to pass to the spawned teammate process."""
    flags: List[str] = []

    if not plan_mode_required:
        # Propagate dangerously-skip-permissions if set in env
        if os.environ.get("CLAUDE_SKIP_PERMISSIONS") == "1":
            flags.append("--dangerously-skip-permissions")

    if model:
        flags.append(f"--model {_shell_quote(model)}")

    return (" " + " ".join(flags)) if flags else ""


def _build_inherited_env_vars() -> str:
    """
    Build an env string of inherited environment variables for the spawn command.
    Mirrors buildInheritedEnvVars in spawnUtils.ts.
    """
    keys = [
        "CLAUDECODE",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "CLAUDE_CODE_TEAMMATE_COMMAND",
    ]
    parts = []
    for key in keys:
        val = os.environ.get(key)
        if val is not None:
            parts.append(f"{key}={_shell_quote(val)}")
    return " ".join(parts)


async def _register_in_team_file(
    team_name: str,
    teammate_id: str,
    sanitized_name: str,
    agent_type: Optional[str],
    model: Optional[str],
    prompt: str,
    color: str,
    plan_mode_required: Optional[bool],
    pane_id: str,
    cwd: str,
    backend_type: BackendType,
) -> None:
    """Add a new member record to the team JSON file."""
    team_file = await read_team_file(team_name)
    if team_file is None:
        raise RuntimeError(
            f'Team "{team_name}" does not exist. '
            "Call spawn_team first to create the team."
        )
    team_file.setdefault("members", []).append(
        {
            "agentId": teammate_id,
            "name": sanitized_name,
            "agentType": agent_type,
            "model": model,
            "prompt": prompt,
            "color": color,
            "planModeRequired": plan_mode_required,
            "joinedAt": int(time.time() * 1000),
            "tmuxPaneId": pane_id,
            "cwd": cwd,
            "subscriptions": [],
            "backendType": backend_type.value,
        }
    )
    await write_team_file(team_name, team_file)


def _iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
