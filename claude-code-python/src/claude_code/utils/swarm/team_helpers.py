"""
Team helpers: file I/O, member management, and team directory operations.

原始 TS: utils/swarm/teamHelpers.ts
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..debug import log_for_debugging
from ..env_utils import get_teams_dir
from ..errors import error_message, get_errno_code
from ..slow_operations import json_parse, json_stringify
from .constants import TEAM_LEAD_NAME

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

TeamAllowedPath = Dict[str, Any]
"""Dict with keys: path, toolName, addedBy, addedAt"""

TeamFile = Dict[str, Any]
"""Dict representing a team config.json"""


# ---------------------------------------------------------------------------
# Name utilities
# ---------------------------------------------------------------------------


def sanitize_name(name: str) -> str:
    """Sanitize a name for use in tmux window names, worktree paths, and file paths.

    Replaces all non-alphanumeric characters with hyphens and lowercases.
    """
    return re.sub(r"[^a-zA-Z0-9]", "-", name).lower()


def sanitize_agent_name(name: str) -> str:
    """Sanitize an agent name for use in deterministic agent IDs.

    Replaces @ with - to prevent ambiguity in the agentName@teamName format.
    """
    return name.replace("@", "-")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def get_team_dir(team_name: str) -> str:
    """Get the path to a team's directory."""
    return os.path.join(get_teams_dir(), sanitize_name(team_name))


def get_team_file_path(team_name: str) -> str:
    """Get the path to a team's config.json file."""
    return os.path.join(get_team_dir(team_name), "config.json")


# ---------------------------------------------------------------------------
# Team file I/O (sync)
# ---------------------------------------------------------------------------


def read_team_file(team_name: str) -> Optional[TeamFile]:
    """Read a team file by name (sync).

    Returns None if the file doesn't exist or cannot be parsed.
    """
    try:
        path = get_team_file_path(team_name)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return json_parse(content)
    except OSError as e:
        if get_errno_code(e) == "ENOENT":
            return None
        log_for_debugging(
            f"[TeammateTool] Failed to read team file for {team_name}: {error_message(e)}"
        )
        return None
    except Exception as e:
        log_for_debugging(
            f"[TeammateTool] Failed to read team file for {team_name}: {error_message(e)}"
        )
        return None


async def read_team_file_async(team_name: str) -> Optional[TeamFile]:
    """Read a team file by name (async)."""
    try:
        path = get_team_file_path(team_name)
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(
            None, lambda: open(path, "r", encoding="utf-8").read()
        )
        return json_parse(content)
    except OSError as e:
        if get_errno_code(e) == "ENOENT":
            return None
        log_for_debugging(
            f"[TeammateTool] Failed to read team file for {team_name}: {error_message(e)}"
        )
        return None
    except Exception as e:
        log_for_debugging(
            f"[TeammateTool] Failed to read team file for {team_name}: {error_message(e)}"
        )
        return None


def _write_team_file(team_name: str, team_file: TeamFile) -> None:
    """Write a team file (sync)."""
    team_dir = get_team_dir(team_name)
    os.makedirs(team_dir, exist_ok=True)
    path = get_team_file_path(team_name)
    content = json_stringify(team_file, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


async def write_team_file_async(team_name: str, team_file: TeamFile) -> None:
    """Write a team file (async)."""
    team_dir = get_team_dir(team_name)
    os.makedirs(team_dir, exist_ok=True)
    path = get_team_file_path(team_name)
    content = json_stringify(team_file, indent=2)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: _sync_write(path, content),
    )


def _sync_write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


def remove_teammate_from_team_file(
    team_name: str,
    identifier: Dict[str, Optional[str]],
) -> bool:
    """Remove a teammate from the team file by agent ID or name.

    Args:
        team_name: The name of the team.
        identifier: Dict with optional 'agentId' and/or 'name' keys.

    Returns:
        True if the member was removed, False otherwise.
    """
    identifier_str = identifier.get("agentId") or identifier.get("name")
    if not identifier_str:
        log_for_debugging(
            "[TeammateTool] remove_teammate_from_team_file called with no identifier"
        )
        return False

    team_file = read_team_file(team_name)
    if not team_file:
        log_for_debugging(
            f"[TeammateTool] Cannot remove teammate {identifier_str}: "
            f'failed to read team file for "{team_name}"'
        )
        return False

    original_length = len(team_file.get("members", []))
    team_file["members"] = [
        m for m in team_file.get("members", [])
        if not (
            (identifier.get("agentId") and m.get("agentId") == identifier["agentId"])
            or (identifier.get("name") and m.get("name") == identifier["name"])
        )
    ]

    if len(team_file["members"]) == original_length:
        log_for_debugging(
            f'[TeammateTool] Teammate {identifier_str} not found in team file for "{team_name}"'
        )
        return False

    _write_team_file(team_name, team_file)
    log_for_debugging(
        f"[TeammateTool] Removed teammate from team file: {identifier_str}"
    )
    return True


def add_hidden_pane_id(team_name: str, pane_id: str) -> bool:
    """Add a pane ID to the hidden panes list in the team file."""
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    hidden_pane_ids: List[str] = team_file.get("hiddenPaneIds") or []
    if pane_id not in hidden_pane_ids:
        hidden_pane_ids.append(pane_id)
        team_file["hiddenPaneIds"] = hidden_pane_ids
        _write_team_file(team_name, team_file)
        log_for_debugging(
            f"[TeammateTool] Added {pane_id} to hidden panes for team {team_name}"
        )
    return True


def remove_hidden_pane_id(team_name: str, pane_id: str) -> bool:
    """Remove a pane ID from the hidden panes list in the team file."""
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    hidden_pane_ids: List[str] = team_file.get("hiddenPaneIds") or []
    if pane_id in hidden_pane_ids:
        hidden_pane_ids.remove(pane_id)
        team_file["hiddenPaneIds"] = hidden_pane_ids
        _write_team_file(team_name, team_file)
        log_for_debugging(
            f"[TeammateTool] Removed {pane_id} from hidden panes for team {team_name}"
        )
    return True


def remove_member_from_team(team_name: str, tmux_pane_id: str) -> bool:
    """Remove a teammate from the team config file by pane ID."""
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    members = team_file.get("members", [])
    idx = next(
        (i for i, m in enumerate(members) if m.get("tmuxPaneId") == tmux_pane_id), -1
    )
    if idx == -1:
        return False

    members.pop(idx)

    # Also remove from hiddenPaneIds
    hidden: List[str] = team_file.get("hiddenPaneIds") or []
    if tmux_pane_id in hidden:
        hidden.remove(tmux_pane_id)
        team_file["hiddenPaneIds"] = hidden

    team_file["members"] = members
    _write_team_file(team_name, team_file)
    log_for_debugging(
        f"[TeammateTool] Removed member with pane {tmux_pane_id} from team {team_name}"
    )
    return True


def remove_member_by_agent_id(team_name: str, agent_id: str) -> bool:
    """Remove a teammate from a team's member list by agent ID.

    Use this for in-process teammates which all share the same tmuxPaneId.
    """
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    members = team_file.get("members", [])
    idx = next((i for i, m in enumerate(members) if m.get("agentId") == agent_id), -1)
    if idx == -1:
        return False

    members.pop(idx)
    team_file["members"] = members
    _write_team_file(team_name, team_file)
    log_for_debugging(
        f"[TeammateTool] Removed member {agent_id} from team {team_name}"
    )
    return True


def set_member_mode(team_name: str, member_name: str, mode: str) -> bool:
    """Set a team member's permission mode."""
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    members = team_file.get("members", [])
    member = next((m for m in members if m.get("name") == member_name), None)
    if not member:
        log_for_debugging(
            f"[TeammateTool] Cannot set member mode: member {member_name} not found in team {team_name}"
        )
        return False

    if member.get("mode") == mode:
        return True

    team_file["members"] = [
        {**m, "mode": mode} if m.get("name") == member_name else m
        for m in members
    ]
    _write_team_file(team_name, team_file)
    log_for_debugging(
        f"[TeammateTool] Set member {member_name} in team {team_name} to mode: {mode}"
    )
    return True


def sync_teammate_mode(mode: str, team_name_override: Optional[str] = None) -> None:
    """Sync the current teammate's mode to config.json so team lead sees it."""
    try:
        from ..teammate import is_teammate, get_team_name, get_agent_name
        if not is_teammate():
            return
        team_name = team_name_override or get_team_name()
        agent_name = get_agent_name()
        if team_name and agent_name:
            set_member_mode(team_name, agent_name, mode)
    except (ImportError, Exception):
        pass


def set_multiple_member_modes(
    team_name: str,
    mode_updates: List[Dict[str, str]],
) -> bool:
    """Set multiple team members' permission modes in a single atomic operation."""
    team_file = read_team_file(team_name)
    if not team_file:
        return False

    update_map = {u["memberName"]: u["mode"] for u in mode_updates}
    any_changed = False

    updated_members = []
    for member in team_file.get("members", []):
        new_mode = update_map.get(member.get("name", ""))
        if new_mode is not None and member.get("mode") != new_mode:
            any_changed = True
            updated_members.append({**member, "mode": new_mode})
        else:
            updated_members.append(member)

    if any_changed:
        team_file["members"] = updated_members
        _write_team_file(team_name, team_file)
        log_for_debugging(
            f"[TeammateTool] Set {len(mode_updates)} member modes in team {team_name}"
        )
    return True


async def set_member_active(
    team_name: str,
    member_name: str,
    is_active: bool,
) -> None:
    """Set a team member's active status (async)."""
    team_file = await read_team_file_async(team_name)
    if not team_file:
        log_for_debugging(
            f"[TeammateTool] Cannot set member active: team {team_name} not found"
        )
        return

    members = team_file.get("members", [])
    member = next((m for m in members if m.get("name") == member_name), None)
    if not member:
        log_for_debugging(
            f"[TeammateTool] Cannot set member active: member {member_name} not found in team {team_name}"
        )
        return

    if member.get("isActive") == is_active:
        return

    member["isActive"] = is_active
    await write_team_file_async(team_name, team_file)
    log_for_debugging(
        f"[TeammateTool] Set member {member_name} in team {team_name} to "
        f"{'active' if is_active else 'idle'}"
    )


# ---------------------------------------------------------------------------
# Session cleanup tracking
# ---------------------------------------------------------------------------


def register_team_for_session_cleanup(team_name: str) -> None:
    """Mark a team as created this session so it gets cleaned up on exit."""
    try:
        from ...bootstrap.state import get_session_created_teams
        get_session_created_teams().add(team_name)
    except (ImportError, Exception):
        pass


def unregister_team_for_session_cleanup(team_name: str) -> None:
    """Remove a team from session cleanup tracking."""
    try:
        from ...bootstrap.state import get_session_created_teams
        get_session_created_teams().discard(team_name)
    except (ImportError, Exception):
        pass


async def cleanup_session_teams() -> None:
    """Clean up all teams created this session that weren't explicitly deleted."""
    try:
        from ...bootstrap.state import get_session_created_teams
        session_created_teams = get_session_created_teams()
    except (ImportError, Exception):
        return

    if not session_created_teams:
        return

    teams = list(session_created_teams)
    log_for_debugging(
        f"cleanup_session_teams: removing {len(teams)} orphan team dir(s): {', '.join(teams)}"
    )

    # Kill panes first
    await asyncio.gather(
        *[_kill_orphaned_teammate_panes(name) for name in teams],
        return_exceptions=True,
    )
    # Then clean directories
    await asyncio.gather(
        *[cleanup_team_directories(name) for name in teams],
        return_exceptions=True,
    )
    session_created_teams.clear()


async def _kill_orphaned_teammate_panes(team_name: str) -> None:
    """Best-effort kill of all pane-backed teammate panes for a team."""
    team_file = read_team_file(team_name)
    if not team_file:
        return

    try:
        from .backends.types import is_pane_backend
    except (ImportError, Exception):
        return

    pane_members = [
        m for m in team_file.get("members", [])
        if m.get("name") != TEAM_LEAD_NAME
        and m.get("tmuxPaneId")
        and m.get("backendType")
        and is_pane_backend(m.get("backendType", ""))
    ]

    if not pane_members:
        return

    try:
        from .backends.detection import is_inside_tmux
        from .backends.registry import ensure_backends_registered, get_backend_by_type
        await ensure_backends_registered()
        use_external_session = not await is_inside_tmux()
    except (ImportError, Exception):
        return

    async def _kill_pane(m: Dict[str, Any]) -> None:
        pane_id = m.get("tmuxPaneId")
        backend_type = m.get("backendType")
        if not pane_id or not backend_type:
            return
        try:
            backend = get_backend_by_type(backend_type)
            ok = await backend.kill_pane(pane_id, use_external_session)
            log_for_debugging(
                f"cleanup_session_teams: killPane {m.get('name')} "
                f"({backend_type} {pane_id}) → {ok}"
            )
        except Exception:
            pass

    await asyncio.gather(*[_kill_pane(m) for m in pane_members], return_exceptions=True)


async def _destroy_worktree(worktree_path: str) -> None:
    """Destroy a git worktree at the given path."""
    git_file_path = os.path.join(worktree_path, ".git")
    main_repo_path: Optional[str] = None

    try:
        with open(git_file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        match = re.match(r"^gitdir:\s*(.+)$", content)
        if match:
            worktree_git_dir = match.group(1)
            main_git_dir = os.path.normpath(
                os.path.join(worktree_git_dir, "..", "..")
            )
            main_repo_path = os.path.normpath(os.path.join(main_git_dir, ".."))
    except Exception:
        pass

    # Try git worktree remove
    if main_repo_path:
        try:
            from ..exec_file_no_throw import exec_file_no_throw
            from ..git import git_exe
            result = await exec_file_no_throw(
                git_exe(),
                ["worktree", "remove", "--force", worktree_path],
                cwd=main_repo_path,
            )
            if result.code == 0:
                log_for_debugging(
                    f"[TeammateTool] Removed worktree via git: {worktree_path}"
                )
                return
            stderr = getattr(result, "stderr", "") or ""
            if "not a working tree" in stderr:
                log_for_debugging(
                    f"[TeammateTool] Worktree already removed: {worktree_path}"
                )
                return
            log_for_debugging(
                f"[TeammateTool] git worktree remove failed, falling back to rm: {stderr}"
            )
        except Exception:
            pass

    # Fallback: remove directory
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: shutil.rmtree(worktree_path, ignore_errors=True),
        )
        log_for_debugging(
            f"[TeammateTool] Removed worktree directory manually: {worktree_path}"
        )
    except Exception as e:
        log_for_debugging(
            f"[TeammateTool] Failed to remove worktree {worktree_path}: {error_message(e)}"
        )


async def cleanup_team_directories(team_name: str) -> None:
    """Clean up team and task directories for a given team name.

    Also cleans up git worktrees created for teammates.
    Called when a swarm session is terminated.
    """
    sanitized_name = sanitize_name(team_name)

    # Read team file to get worktree paths BEFORE deleting the team directory
    team_file = read_team_file(team_name)
    worktree_paths: List[str] = []
    if team_file:
        for member in team_file.get("members", []):
            wt = member.get("worktreePath")
            if wt:
                worktree_paths.append(wt)

    # Clean up worktrees first
    for worktree_path in worktree_paths:
        await _destroy_worktree(worktree_path)

    # Clean up team directory
    team_dir = get_team_dir(team_name)
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: shutil.rmtree(team_dir, ignore_errors=True),
        )
        log_for_debugging(
            f"[TeammateTool] Cleaned up team directory: {team_dir}"
        )
    except Exception as e:
        log_for_debugging(
            f"[TeammateTool] Failed to clean up team directory {team_dir}: {error_message(e)}"
        )

    # Clean up tasks directory
    try:
        from ..tasks import get_tasks_dir, notify_tasks_updated  # type: ignore[import]
        tasks_dir = get_tasks_dir(sanitized_name)
        try:
            await loop.run_in_executor(
                None,
                lambda: shutil.rmtree(tasks_dir, ignore_errors=True),
            )
            log_for_debugging(
                f"[TeammateTool] Cleaned up tasks directory: {tasks_dir}"
            )
            notify_tasks_updated()
        except Exception as e:
            log_for_debugging(
                f"[TeammateTool] Failed to clean up tasks directory {tasks_dir}: {error_message(e)}"
            )
    except (ImportError, Exception):
        pass
