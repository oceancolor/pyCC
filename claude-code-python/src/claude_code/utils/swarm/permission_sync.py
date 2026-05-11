"""
Synchronized Permission Prompts for Agent Swarms.

Provides infrastructure for coordinating permission prompts across
multiple agents in a swarm. When a worker agent needs permission for a tool use,
it can forward the request to the team leader, who can then approve or deny it.

Flow:
1. Worker agent encounters a permission prompt
2. Worker sends a permission_request message to the leader's mailbox
3. Leader polls for mailbox messages and detects permission requests
4. User approves/denies via the leader's UI
5. Leader sends a permission_response message to the worker's mailbox
6. Worker polls mailbox for responses and continues execution

原始 TS: utils/swarm/permissionSync.ts
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..debug import log_for_debugging
from ..errors import get_errno_code
from ..log import log_error
from ..slow_operations import json_parse, json_stringify
from .team_helpers import get_team_dir, read_team_file_async


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class SwarmPermissionRequest:
    """Full request schema for a permission request from a worker to the leader."""

    id: str
    worker_id: str
    worker_name: str
    team_name: str
    tool_name: str
    tool_use_id: str
    description: str
    input: Dict[str, Any]
    permission_suggestions: List[Any]
    status: str  # 'pending' | 'approved' | 'rejected'
    created_at: int

    worker_color: Optional[str] = None
    resolved_by: Optional[str] = None  # 'worker' | 'leader'
    resolved_at: Optional[int] = None
    feedback: Optional[str] = None
    updated_input: Optional[Dict[str, Any]] = None
    permission_updates: Optional[List[Any]] = None


@dataclass
class PermissionResolution:
    """Resolution data returned when leader/worker resolves a request."""

    decision: str  # 'approved' | 'rejected'
    resolved_by: str  # 'worker' | 'leader'
    feedback: Optional[str] = None
    updated_input: Optional[Dict[str, Any]] = None
    permission_updates: Optional[List[Any]] = None


@dataclass
class PermissionResponse:
    """Legacy response type for worker polling."""

    request_id: str
    decision: str  # 'approved' | 'denied'
    timestamp: str
    feedback: Optional[str] = None
    updated_input: Optional[Dict[str, Any]] = None
    permission_updates: Optional[List[Any]] = None


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def get_permission_dir(team_name: str) -> str:
    """Get the base directory for a team's permission requests."""
    return os.path.join(get_team_dir(team_name), "permissions")


def _get_pending_dir(team_name: str) -> str:
    return os.path.join(get_permission_dir(team_name), "pending")


def _get_resolved_dir(team_name: str) -> str:
    return os.path.join(get_permission_dir(team_name), "resolved")


async def _ensure_permission_dirs(team_name: str) -> None:
    """Ensure the permissions directory structure exists."""
    for d in [get_permission_dir(team_name), _get_pending_dir(team_name), _get_resolved_dir(team_name)]:
        os.makedirs(d, exist_ok=True)


def _get_pending_request_path(team_name: str, request_id: str) -> str:
    return os.path.join(_get_pending_dir(team_name), f"{request_id}.json")


def _get_resolved_request_path(team_name: str, request_id: str) -> str:
    return os.path.join(_get_resolved_dir(team_name), f"{request_id}.json")


# ---------------------------------------------------------------------------
# Request ID generators
# ---------------------------------------------------------------------------


def generate_request_id() -> str:
    """Generate a unique request ID."""
    ts = int(time.time() * 1000)
    rnd = random.randint(0, 2**31)
    return f"perm-{ts}-{hex(rnd)[2:]}"


def generate_sandbox_request_id() -> str:
    """Generate a unique sandbox permission request ID."""
    ts = int(time.time() * 1000)
    rnd = random.randint(0, 2**31)
    return f"sandbox-{ts}-{hex(rnd)[2:]}"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_permission_request(
    tool_name: str,
    tool_use_id: str,
    input: Dict[str, Any],
    description: str,
    permission_suggestions: Optional[List[Any]] = None,
    team_name: Optional[str] = None,
    worker_id: Optional[str] = None,
    worker_name: Optional[str] = None,
    worker_color: Optional[str] = None,
) -> SwarmPermissionRequest:
    """Create a new SwarmPermissionRequest object."""
    try:
        from ..teammate import get_team_name, get_agent_id, get_agent_name, get_teammate_color
        _team_name = team_name or get_team_name()
        _worker_id = worker_id or get_agent_id()
        _worker_name = worker_name or get_agent_name()
        _worker_color = worker_color or get_teammate_color()
    except (ImportError, Exception):
        _team_name = team_name
        _worker_id = worker_id
        _worker_name = worker_name
        _worker_color = worker_color

    if not _team_name:
        raise ValueError("Team name is required for permission requests")
    if not _worker_id:
        raise ValueError("Worker ID is required for permission requests")
    if not _worker_name:
        raise ValueError("Worker name is required for permission requests")

    return SwarmPermissionRequest(
        id=generate_request_id(),
        worker_id=_worker_id,
        worker_name=_worker_name,
        worker_color=_worker_color,
        team_name=_team_name,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        description=description,
        input=input,
        permission_suggestions=permission_suggestions or [],
        status="pending",
        created_at=int(time.time() * 1000),
    )


# ---------------------------------------------------------------------------
# File-based pending/resolved I/O
# ---------------------------------------------------------------------------


def _request_to_dict(req: SwarmPermissionRequest) -> Dict[str, Any]:
    return {
        "id": req.id,
        "workerId": req.worker_id,
        "workerName": req.worker_name,
        "workerColor": req.worker_color,
        "teamName": req.team_name,
        "toolName": req.tool_name,
        "toolUseId": req.tool_use_id,
        "description": req.description,
        "input": req.input,
        "permissionSuggestions": req.permission_suggestions,
        "status": req.status,
        "createdAt": req.created_at,
        "resolvedBy": req.resolved_by,
        "resolvedAt": req.resolved_at,
        "feedback": req.feedback,
        "updatedInput": req.updated_input,
        "permissionUpdates": req.permission_updates,
    }


def _dict_to_request(d: Dict[str, Any]) -> Optional[SwarmPermissionRequest]:
    try:
        return SwarmPermissionRequest(
            id=d["id"],
            worker_id=d["workerId"],
            worker_name=d["workerName"],
            worker_color=d.get("workerColor"),
            team_name=d["teamName"],
            tool_name=d["toolName"],
            tool_use_id=d["toolUseId"],
            description=d["description"],
            input=d.get("input", {}),
            permission_suggestions=d.get("permissionSuggestions", []),
            status=d.get("status", "pending"),
            created_at=d.get("createdAt", 0),
            resolved_by=d.get("resolvedBy"),
            resolved_at=d.get("resolvedAt"),
            feedback=d.get("feedback"),
            updated_input=d.get("updatedInput"),
            permission_updates=d.get("permissionUpdates"),
        )
    except (KeyError, Exception):
        return None


async def write_permission_request(
    request: SwarmPermissionRequest,
) -> SwarmPermissionRequest:
    """Write a permission request to the pending directory with file locking.

    Called by worker agents when they need permission approval from the leader.
    """
    await _ensure_permission_dirs(request.team_name)
    pending_path = _get_pending_request_path(request.team_name, request.id)
    lock_dir = _get_pending_dir(request.team_name)
    lock_file_path = os.path.join(lock_dir, ".lock")

    # Ensure lock file exists
    open(lock_file_path, "a").close()

    try:
        from ..lockfile import lock as _lock
        release = await _lock(lock_file_path)
        try:
            with open(pending_path, "w", encoding="utf-8") as f:
                f.write(json_stringify(_request_to_dict(request), indent=2))
            log_for_debugging(
                f"[PermissionSync] Wrote pending request {request.id} from "
                f"{request.worker_name} for {request.tool_name}"
            )
        finally:
            await release.release()
    except Exception as e:
        log_for_debugging(f"[PermissionSync] Failed to write permission request: {e}")
        log_error(e)
        raise

    return request


# Alias for backward compatibility
submit_permission_request = write_permission_request


async def read_pending_permissions(
    team_name: Optional[str] = None,
) -> List[SwarmPermissionRequest]:
    """Read all pending permission requests for a team.

    Called by the team leader to see what requests need attention.
    """
    try:
        from ..teammate import get_team_name
        team = team_name or get_team_name()
    except (ImportError, Exception):
        team = team_name

    if not team:
        log_for_debugging("[PermissionSync] No team name available")
        return []

    pending_dir = _get_pending_dir(team)

    try:
        files = os.listdir(pending_dir)
    except OSError as e:
        if get_errno_code(e) == "ENOENT":
            return []
        log_for_debugging(f"[PermissionSync] Failed to read pending requests: {e}")
        log_error(e)
        return []

    json_files = [f for f in files if f.endswith(".json") and f != ".lock"]

    results: List[Optional[SwarmPermissionRequest]] = []
    for fname in json_files:
        fpath = os.path.join(pending_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            parsed = json_parse(content)
            req = _dict_to_request(parsed)
            results.append(req)
        except Exception as err:
            log_for_debugging(
                f"[PermissionSync] Failed to read request file {fname}: {err}"
            )
            results.append(None)

    requests = [r for r in results if r is not None]
    requests.sort(key=lambda r: r.created_at)
    return requests


async def read_resolved_permission(
    request_id: str,
    team_name: Optional[str] = None,
) -> Optional[SwarmPermissionRequest]:
    """Read a resolved permission request by ID."""
    try:
        from ..teammate import get_team_name
        team = team_name or get_team_name()
    except (ImportError, Exception):
        team = team_name

    if not team:
        return None

    resolved_path = _get_resolved_request_path(team, request_id)

    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            content = f.read()
        parsed = json_parse(content)
        return _dict_to_request(parsed)
    except OSError as e:
        if get_errno_code(e) == "ENOENT":
            return None
        log_for_debugging(
            f"[PermissionSync] Failed to read resolved request {request_id}: {e}"
        )
        log_error(e)
        return None
    except Exception as e:
        log_for_debugging(
            f"[PermissionSync] Failed to read resolved request {request_id}: {e}"
        )
        return None


async def resolve_permission(
    request_id: str,
    resolution: PermissionResolution,
    team_name: Optional[str] = None,
) -> bool:
    """Resolve a permission request. Called by the team leader or worker."""
    try:
        from ..teammate import get_team_name
        team = team_name or get_team_name()
    except (ImportError, Exception):
        team = team_name

    if not team:
        log_for_debugging("[PermissionSync] No team name available")
        return False

    await _ensure_permission_dirs(team)
    pending_path = _get_pending_request_path(team, request_id)
    resolved_path = _get_resolved_request_path(team, request_id)
    lock_file_path = os.path.join(_get_pending_dir(team), ".lock")

    open(lock_file_path, "a").close()

    try:
        from ..lockfile import lock as _lock
        release = await _lock(lock_file_path)
        try:
            # Read the pending request
            try:
                with open(pending_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError as e:
                if get_errno_code(e) == "ENOENT":
                    log_for_debugging(
                        f"[PermissionSync] Pending request not found: {request_id}"
                    )
                    return False
                raise

            parsed = json_parse(content)
            request = _dict_to_request(parsed)
            if not request:
                log_for_debugging(
                    f"[PermissionSync] Invalid pending request {request_id}"
                )
                return False

            # Update with resolution
            request.status = "approved" if resolution.decision == "approved" else "rejected"
            request.resolved_by = resolution.resolved_by
            request.resolved_at = int(time.time() * 1000)
            request.feedback = resolution.feedback
            request.updated_input = resolution.updated_input
            request.permission_updates = resolution.permission_updates

            # Write to resolved
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(json_stringify(_request_to_dict(request), indent=2))

            # Remove from pending
            os.unlink(pending_path)

            log_for_debugging(
                f"[PermissionSync] Resolved request {request_id} with {resolution.decision}"
            )
            return True
        finally:
            await release.release()
    except Exception as e:
        log_for_debugging(f"[PermissionSync] Failed to resolve request: {e}")
        log_error(e)
        return False


async def cleanup_old_resolutions(
    team_name: Optional[str] = None,
    max_age_ms: int = 3600000,
) -> int:
    """Clean up old resolved permission files."""
    try:
        from ..teammate import get_team_name
        team = team_name or get_team_name()
    except (ImportError, Exception):
        team = team_name

    if not team:
        return 0

    resolved_dir = _get_resolved_dir(team)

    try:
        files = os.listdir(resolved_dir)
    except OSError as e:
        if get_errno_code(e) == "ENOENT":
            return 0
        log_for_debugging(f"[PermissionSync] Failed to cleanup resolutions: {e}")
        log_error(e)
        return 0

    now = int(time.time() * 1000)
    json_files = [f for f in files if f.endswith(".json")]
    cleaned = 0

    for fname in json_files:
        fpath = os.path.join(resolved_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            parsed = json_parse(content)
            resolved_at = parsed.get("resolvedAt") or parsed.get("createdAt", 0)
            if now - resolved_at >= max_age_ms:
                os.unlink(fpath)
                log_for_debugging(f"[PermissionSync] Cleaned up old resolution: {fname}")
                cleaned += 1
        except Exception:
            try:
                os.unlink(fpath)
                cleaned += 1
            except Exception:
                pass

    if cleaned > 0:
        log_for_debugging(f"[PermissionSync] Cleaned up {cleaned} old resolutions")

    return cleaned


async def delete_resolved_permission(
    request_id: str,
    team_name: Optional[str] = None,
) -> bool:
    """Delete a resolved permission file after a worker has processed the resolution."""
    try:
        from ..teammate import get_team_name
        team = team_name or get_team_name()
    except (ImportError, Exception):
        team = team_name

    if not team:
        return False

    resolved_path = _get_resolved_request_path(team, request_id)

    try:
        os.unlink(resolved_path)
        log_for_debugging(
            f"[PermissionSync] Deleted resolved permission: {request_id}"
        )
        return True
    except OSError as e:
        if get_errno_code(e) == "ENOENT":
            return False
        log_for_debugging(
            f"[PermissionSync] Failed to delete resolved permission: {e}"
        )
        log_error(e)
        return False


async def poll_for_response(
    request_id: str,
    _agent_name: Optional[str] = None,
    team_name: Optional[str] = None,
) -> Optional[PermissionResponse]:
    """Poll for a permission response (worker-side convenience function)."""
    resolved = await read_resolved_permission(request_id, team_name)
    if not resolved:
        return None

    ts = (
        _ms_to_iso(resolved.resolved_at)
        if resolved.resolved_at
        else _ms_to_iso(resolved.created_at)
    )
    return PermissionResponse(
        request_id=resolved.id,
        decision="approved" if resolved.status == "approved" else "denied",
        timestamp=ts,
        feedback=resolved.feedback,
        updated_input=resolved.updated_input,
        permission_updates=resolved.permission_updates,
    )


async def remove_worker_response(
    request_id: str,
    _agent_name: Optional[str] = None,
    team_name: Optional[str] = None,
) -> None:
    """Remove a worker's response after processing (alias for delete_resolved_permission)."""
    await delete_resolved_permission(request_id, team_name)


def _ms_to_iso(ms: int) -> str:
    import datetime
    dt = datetime.datetime.utcfromtimestamp(ms / 1000.0)
    return dt.isoformat() + "Z"


# ---------------------------------------------------------------------------
# Leadership checks
# ---------------------------------------------------------------------------


def is_team_leader(team_name: Optional[str] = None) -> bool:
    """Check if the current agent is a team leader."""
    try:
        from ..teammate import get_team_name, get_agent_id
        team = team_name or get_team_name()
        if not team:
            return False
        agent_id = get_agent_id()
        return not agent_id or agent_id == "team-lead"
    except (ImportError, Exception):
        return False


def is_swarm_worker() -> bool:
    """Check if the current agent is a worker in a swarm."""
    try:
        from ..teammate import get_team_name, get_agent_id
        team_name = get_team_name()
        agent_id = get_agent_id()
        return bool(team_name and agent_id and not is_team_leader())
    except (ImportError, Exception):
        return False


# ---------------------------------------------------------------------------
# Mailbox-based permission system
# ---------------------------------------------------------------------------


async def get_leader_name(team_name: Optional[str] = None) -> Optional[str]:
    """Get the leader's name from the team file."""
    try:
        from ..teammate import get_team_name
        team = team_name or get_team_name()
    except (ImportError, Exception):
        team = team_name

    if not team:
        return None

    team_file = await read_team_file_async(team)
    if not team_file:
        log_for_debugging(f"[PermissionSync] Team file not found for team: {team}")
        return None

    lead_agent_id = team_file.get("leadAgentId")
    members = team_file.get("members", [])
    lead_member = next((m for m in members if m.get("agentId") == lead_agent_id), None)
    return lead_member.get("name", "team-lead") if lead_member else "team-lead"


async def send_permission_request_via_mailbox(
    request: SwarmPermissionRequest,
) -> bool:
    """Send a permission request to the leader via mailbox."""
    leader_name = await get_leader_name(request.team_name)
    if not leader_name:
        log_for_debugging(
            "[PermissionSync] Cannot send permission request: leader name not found"
        )
        return False

    try:
        from ..teammate_mailbox import (
            create_permission_request_message,
            write_to_mailbox,
        )

        message = create_permission_request_message(
            request_id=request.id,
            agent_id=request.worker_name,
            tool_name=request.tool_name,
            tool_use_id=request.tool_use_id,
            description=request.description,
            input=request.input,
            permission_suggestions=request.permission_suggestions,
        )

        import datetime
        await write_to_mailbox(
            leader_name,
            {
                "from": request.worker_name,
                "text": json_stringify(message),
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "color": request.worker_color,
            },
            request.team_name,
        )

        log_for_debugging(
            f"[PermissionSync] Sent permission request {request.id} to leader "
            f"{leader_name} via mailbox"
        )
        return True
    except Exception as e:
        log_for_debugging(
            f"[PermissionSync] Failed to send permission request via mailbox: {e}"
        )
        log_error(e)
        return False


async def send_permission_response_via_mailbox(
    worker_name: str,
    resolution: PermissionResolution,
    request_id: str,
    team_name: Optional[str] = None,
) -> bool:
    """Send a permission response to a worker via mailbox."""
    try:
        from ..teammate import get_team_name
        team = team_name or get_team_name()
    except (ImportError, Exception):
        team = team_name

    if not team:
        log_for_debugging(
            "[PermissionSync] Cannot send permission response: team name not found"
        )
        return False

    try:
        from ..teammate_mailbox import (
            create_permission_response_message,
            write_to_mailbox,
        )
        from ..teammate import get_agent_name

        message = create_permission_response_message(
            request_id=request_id,
            subtype="success" if resolution.decision == "approved" else "error",
            error=resolution.feedback,
            updated_input=resolution.updated_input,
            permission_updates=resolution.permission_updates,
        )

        sender_name = "team-lead"
        try:
            sender_name = get_agent_name() or "team-lead"
        except Exception:
            pass

        import datetime
        await write_to_mailbox(
            worker_name,
            {
                "from": sender_name,
                "text": json_stringify(message),
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            },
            team,
        )

        log_for_debugging(
            f"[PermissionSync] Sent permission response for {request_id} to worker "
            f"{worker_name} via mailbox"
        )
        return True
    except Exception as e:
        log_for_debugging(
            f"[PermissionSync] Failed to send permission response via mailbox: {e}"
        )
        log_error(e)
        return False


async def send_sandbox_permission_request_via_mailbox(
    host: str,
    request_id: str,
    team_name: Optional[str] = None,
) -> bool:
    """Send a sandbox permission request to the leader via mailbox."""
    try:
        from ..teammate import get_team_name
        team = team_name or get_team_name()
    except (ImportError, Exception):
        team = team_name

    if not team:
        log_for_debugging(
            "[PermissionSync] Cannot send sandbox permission request: team name not found"
        )
        return False

    leader_name = await get_leader_name(team)
    if not leader_name:
        log_for_debugging(
            "[PermissionSync] Cannot send sandbox permission request: leader name not found"
        )
        return False

    worker_id: Optional[str] = None
    worker_name: Optional[str] = None
    worker_color: Optional[str] = None
    try:
        from ..teammate import get_agent_id, get_agent_name, get_teammate_color
        worker_id = get_agent_id()
        worker_name = get_agent_name()
        worker_color = get_teammate_color()
    except (ImportError, Exception):
        pass

    if not worker_id or not worker_name:
        log_for_debugging(
            "[PermissionSync] Cannot send sandbox permission request: worker ID or name not found"
        )
        return False

    try:
        from ..teammate_mailbox import (
            create_sandbox_permission_request_message,
            write_to_mailbox,
        )

        message = create_sandbox_permission_request_message(
            request_id=request_id,
            worker_id=worker_id,
            worker_name=worker_name,
            worker_color=worker_color,
            host=host,
        )

        import datetime
        await write_to_mailbox(
            leader_name,
            {
                "from": worker_name,
                "text": json_stringify(message),
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "color": worker_color,
            },
            team,
        )

        log_for_debugging(
            f"[PermissionSync] Sent sandbox permission request {request_id} for host "
            f"{host} to leader {leader_name} via mailbox"
        )
        return True
    except Exception as e:
        log_for_debugging(
            f"[PermissionSync] Failed to send sandbox permission request via mailbox: {e}"
        )
        log_error(e)
        return False


async def send_sandbox_permission_response_via_mailbox(
    worker_name: str,
    request_id: str,
    host: str,
    allow: bool,
    team_name: Optional[str] = None,
) -> bool:
    """Send a sandbox permission response to a worker via mailbox."""
    try:
        from ..teammate import get_team_name
        team = team_name or get_team_name()
    except (ImportError, Exception):
        team = team_name

    if not team:
        log_for_debugging(
            "[PermissionSync] Cannot send sandbox permission response: team name not found"
        )
        return False

    try:
        from ..teammate_mailbox import (
            create_sandbox_permission_response_message,
            write_to_mailbox,
        )
        from ..teammate import get_agent_name

        message = create_sandbox_permission_response_message(
            request_id=request_id,
            host=host,
            allow=allow,
        )

        sender_name = "team-lead"
        try:
            sender_name = get_agent_name() or "team-lead"
        except Exception:
            pass

        import datetime
        await write_to_mailbox(
            worker_name,
            {
                "from": sender_name,
                "text": json_stringify(message),
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            },
            team,
        )

        log_for_debugging(
            f"[PermissionSync] Sent sandbox permission response for {request_id} "
            f"(host: {host}, allow: {allow}) to worker {worker_name} via mailbox"
        )
        return True
    except Exception as e:
        log_for_debugging(
            f"[PermissionSync] Failed to send sandbox permission response via mailbox: {e}"
        )
        log_error(e)
        return False
